"""Edge cases and failure modes for every public surface: tools, LLM backends, agent loop, CLI, harness."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bench import harness
from bench.harness import BUGS, run_case, summarize
from vericode import cli
from vericode.agent import Agent, AgentConfig, parse_action
from vericode.llm import MockLLM, OllamaLLM, ScriptedLLM, make_llm
from vericode.tools import Workspace, run_pytest
from vericode.trajectory import Trajectory

CASE = BUGS / "bug01_pagination"


def act(tool, **args):
    return json.dumps({"tool": tool, "args": args})


@pytest.fixture()
def ws():
    w = Workspace(CASE / "repo")
    yield w
    w.cleanup()


# ------------------------------------------------------------------ every tool, happy path and error path
def test_list_and_read_file(ws):
    files = ws.call("list_files", {}).splitlines()
    assert any(f.endswith(".py") for f in files)
    src = next(f for f in files if not f.startswith("tests/") and f.endswith(".py"))
    out = ws.call("read_file", {"path": src})
    assert out.startswith("   1 |") or "|" in out
    assert "(empty file)" not in out
    assert ws.call("read_file", {"path": src, "start": 2, "end": 3}).count("\n") <= 1
    assert ws.call("read_file", {"path": "nope.py"}).startswith("ERROR")
    assert ws.call("read_file", {"path": ""}).startswith("ERROR")


def test_read_empty_file(ws):
    ws.call("write_file", {"path": "empty.txt", "content": ""})
    assert ws.call("read_file", {"path": "empty.txt"}) == "(empty file)"


def test_search_code(ws):
    assert ":" in ws.call("search_code", {"pattern": "def "})
    assert ws.call("search_code", {"pattern": "zzzz_never_present"}) == "(no matches)"
    assert "bad regex" in ws.call("search_code", {"pattern": "("})
    assert ws.call("search_code", {"pattern": "def ", "glob": "*.nothing"}) == "(no matches)"


def test_edit_file_error_paths(ws):
    ws.call("write_file", {"path": "m.py", "content": "a = 1\nb = 1\n"})
    assert ws.call("edit_file", {"path": "m.py", "old": "a = 1", "new": "a = 2"}) == "edited m.py"
    assert "not found" in ws.call("edit_file", {"path": "m.py", "old": "zzz", "new": "y"})
    ws.call("write_file", {"path": "dup.py", "content": "x\nx\n"})
    assert "matches 2 places" in ws.call("edit_file", {"path": "dup.py", "old": "x", "new": "y"})
    assert "non-empty" in ws.call("edit_file", {"path": "m.py", "old": "", "new": "y"})
    assert "does not exist" in ws.call("edit_file", {"path": "ghost.py", "old": "a", "new": "b"})


def test_write_file_creates_nested_dirs_and_blocks_git(ws):
    assert ws.call("write_file", {"path": "pkg/sub/mod.py", "content": "x = 1\n"}).startswith("wrote pkg/sub/mod.py")
    assert (ws.root / "pkg/sub/mod.py").read_text() == "x = 1\n"
    assert "cannot write inside .git" in ws.call("write_file", {"path": ".git/config", "content": "x"})


def test_create_test_sanitises_name_and_runs(ws):
    out = ws.call("create_test", {"name": "../../evil name!", "code": "def test_ok():\n    assert True"})
    assert out.startswith("created tests/test_adv_")
    assert ".." not in out and "!" not in out
    rel = out.split()[-1]
    assert (ws.root / rel).is_file()
    assert "1 passed" in ws.call("run_tests", {"path": rel})


def test_diff_rollback_roundtrip(ws):
    assert ws.call("diff", {}) == "(no changes)"
    src = next(f for f in ws.call("list_files", {}).splitlines() if not f.startswith("tests/") and f.endswith(".py"))
    original = (ws.root / src).read_text()
    ws.call("write_file", {"path": src, "content": original + "\n# changed\n"})
    ws.call("write_file", {"path": "new_file.py", "content": "z = 1\n"})
    assert "# changed" in ws.call("diff", {})
    assert ws.patch_lines() >= 2
    assert set(ws.changed_source_files()) == {src, "new_file.py"}
    assert ws.call("rollback", {"path": src}) == f"restored {src}"
    assert (ws.root / src).read_text() == original
    assert ws.call("rollback", {"path": "new_file.py"}) == "deleted new_file.py"
    assert "does not exist" in ws.call("rollback", {"path": "new_file.py"})
    ws.call("write_file", {"path": "another.py", "content": "q = 1\n"})
    assert "restored all files" in ws.call("rollback", {})
    assert ws.call("diff", {}) == "(no changes)" and not (ws.root / "another.py").exists()


def test_unknown_tool_and_bad_arguments(ws):
    assert "unknown tool" in ws.call("format_disk", {})
    assert "bad arguments" in ws.call("read_file", {"wrong": 1})
    assert "bad arguments" in ws.call("read_file", {})


def test_read_non_utf8_file_does_not_crash(ws):
    (ws.root / "blob.bin").write_bytes(b"\xff\xfe\x00\x80")
    assert ws.call("read_file", {"path": "blob.bin"}).startswith("ERROR")


def test_run_pytest_timeout(tmp_path):
    (tmp_path / "test_slow.py").write_text("import time\ndef test_slow():\n    time.sleep(30)\n")
    res = run_pytest(tmp_path, timeout=2)
    assert res.timed_out and res.summary() == "TIMEOUT" and not res.ok


def test_run_pytest_skips_are_not_passes(tmp_path):
    (tmp_path / "test_skip.py").write_text("import pytest\n@pytest.mark.skip\ndef test_s():\n    assert False\n")
    res = run_pytest(tmp_path)
    assert (res.passed, res.failed, res.errors) == (0, 0, 0)


def test_run_pytest_errors_counted_separately(tmp_path):
    (tmp_path / "test_fx.py").write_text(
        "import pytest\n@pytest.fixture\ndef boom():\n    raise RuntimeError\ndef test_e(boom):\n    pass\n"
        "def test_f():\n    assert False\ndef test_p():\n    pass\n")
    res = run_pytest(tmp_path)
    assert (res.passed, res.failed, res.errors) == (1, 1, 1) and not res.ok


def test_workspace_cleanup_is_idempotent():
    w = Workspace(CASE / "repo")
    root = w.root
    w.cleanup()
    w.cleanup()
    assert not root.exists()


# ------------------------------------------------------------------ LLM backends
class _Stub(BaseHTTPRequestHandler):
    mode = "ok"

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).last = body
        if type(self).mode == "500":
            self.send_response(500)
            self.end_headers()
            return
        payload = b"not json" if type(self).mode == "garbage" else json.dumps(
            {"message": {"content": "hello"}, "prompt_eval_count": 7, "eval_count": 3}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


@pytest.fixture()
def stub_server():
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_ollama_client_roundtrip(stub_server):
    _, host = stub_server
    _Stub.mode = "ok"
    r = OllamaLLM(model="m", host=host, seed=5, temperature=0.1, timeout=5).chat([{"role": "user", "content": "hi"}])
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("hello", 7, 3)
    assert _Stub.last["model"] == "m" and _Stub.last["stream"] is False
    assert _Stub.last["options"] == {"temperature": 0.1, "seed": 5}


@pytest.mark.parametrize("mode", ["500", "garbage"])
def test_ollama_client_surfaces_server_errors(stub_server, mode):
    _, host = stub_server
    _Stub.mode = mode
    with pytest.raises((OSError, ValueError)):
        OllamaLLM(host=host, timeout=5).chat([{"role": "user", "content": "x"}])


def test_make_llm_specs():
    assert isinstance(make_llm("ollama:qwen2.5-coder:7b"), OllamaLLM)
    assert make_llm("ollama:qwen2.5-coder:7b").model == "qwen2.5-coder:7b"
    assert make_llm("ollama:").model == "llama3.1:8b"
    assert isinstance(make_llm("mock:oracle"), MockLLM) and make_llm("mock:").kind == "noop"
    with pytest.raises(ValueError):
        make_llm("openai:gpt")


def test_scripted_llm_accepts_callables_and_exhausts_cleanly():
    llm = ScriptedLLM([lambda msgs: "from-callable"])
    assert llm.chat([]).text == "from-callable"
    assert json.loads(llm.chat([]).text)["tool"] == "finish"


# ------------------------------------------------------------------ agent loop
def test_parse_action_variants():
    assert parse_action('noise {"tool": "run_tests", "args": {}} trailing')["tool"] == "run_tests"
    assert parse_action("```json\n{\"tool\": \"finish\"}\n```")["tool"] == "finish"
    assert parse_action('{"tool": 5}') is None and parse_action("no json") is None and parse_action("{broken") is None
    assert parse_action('{"a": 1} {"tool": "x"}')["tool"] == "x"


def _run_agent(responses, **cfg):
    w = Workspace(CASE / "repo")
    traj = Trajectory()
    try:
        res = Agent(ScriptedLLM(responses), w, AgentConfig(**cfg), traj).run("fix it")
        return res, traj
    finally:
        w.cleanup()


def test_agent_survives_garbage_then_recovers():
    res, traj = _run_agent(["I refuse to emit JSON", act("no_such_tool"), act("read_file", path="missing.py"),
                            act("finish", summary="ok")])
    assert res.claimed_done and res.steps_used == 4
    assert any(e["kind"] == "format_error" for e in traj.steps)


def test_agent_non_dict_args_are_tolerated():
    res, _ = _run_agent([json.dumps({"tool": "list_files", "args": "oops"}), act("finish", summary="x")])
    assert res.claimed_done


def test_agent_step_budget_stops_runaway_loop():
    res, _ = _run_agent([act("list_files")] * 50, max_steps=4)
    assert not res.claimed_done and res.steps_used == 4


def test_verified_mode_feedback_loop_uses_rounds():
    # finish immediately with a failing visible suite -> feedback -> finish again, bounded by max_rounds
    res, traj = _run_agent([act("finish", summary="a"), act("finish", summary="b"), act("finish", summary="c")],
                           verify=True, max_rounds=2)
    assert res.claimed_done and res.rounds <= 2
    assert any(e.get("result") == "suite_failing" for e in traj.steps if e["kind"] == "verify")


# ------------------------------------------------------------------ CLI
def test_cli_requires_issue_and_repo(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--repo", str(CASE / "repo")])
    assert e.value.code == 2


def test_cli_issue_file_and_oracle_exit_zero(tmp_path):
    fixes = harness.load_fixes(CASE)
    assert fixes
    issue = tmp_path / "issue.md"
    issue.write_text((CASE / "issue.md").read_text())
    # mock:oracle in the CLI has no fixes, so it cannot solve the bug -> exit 1 (honest failure, not a crash)
    rc = cli.main(["--repo", str(CASE / "repo"), "--issue-file", str(issue), "--llm", "mock:oracle",
                   "--traj-out", str(tmp_path / "t.json"), "--patch-out", str(tmp_path / "p.diff")])
    assert rc == 1 and json.loads((tmp_path / "t.json").read_text())
    assert (tmp_path / "p.diff").exists()


def test_cli_reports_unreachable_model_server(tmp_path, capsys, monkeypatch):
    def boom(*_a, **_k):
        raise ConnectionRefusedError("refused")
    monkeypatch.setattr(OllamaLLM, "chat", boom)
    rc = cli.main(["--repo", str(CASE / "repo"), "--issue", "x", "--llm", "ollama:m",
                   "--traj-out", str(tmp_path / "t.json"), "--patch-out", str(tmp_path / "p.diff")])
    assert rc == 2 and "Could not reach the model server" in capsys.readouterr().out


def test_cli_unknown_llm_spec_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        cli.main(["--repo", str(CASE / "repo"), "--issue", "x", "--llm", "bogus:x",
                  "--traj-out", str(tmp_path / "t.json"), "--patch-out", str(tmp_path / "p.diff")])


# ------------------------------------------------------------------ harness
def test_harness_main_end_to_end_writes_all_artifacts(tmp_path, capsys):
    out = tmp_path / "run"
    assert harness.main(["--llm", "mock:oracle", "--cases", "pagination,retry", "--out", str(out)]) == 0
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and all(r["resolved"] for r in rows)
    assert (out / "summary.md").read_text().startswith("| mode |")
    assert len(list((out / "trajectories").glob("*.json"))) == 4


def test_harness_noop_is_fully_unresolved_with_full_false_acceptance(tmp_path):
    out = tmp_path / "noop"
    harness.main(["--llm", "mock:noop", "--modes", "baseline", "--cases", "memoize", "--out", str(out)])
    row = json.loads((out / "results.jsonl").read_text().splitlines()[0])
    assert row["resolved"] is False and row["claimed_done"] is True and row["false_acceptance"] is True


def test_harness_rejects_missing_bug_dir(capsys):
    with pytest.raises(SystemExit) as e:
        harness.main(["--bugs-dir", "/definitely/not/here"])
    assert e.value.code == 2


def test_run_case_records_crashes_instead_of_raising():
    class Exploding(ScriptedLLM):
        def chat(self, messages):
            raise RuntimeError("model blew up")
    row = run_case(CASE, "baseline", Exploding([]), AgentConfig())
    assert row["resolved"] is False and "RuntimeError" in row["error"]


def test_summarize_handles_empty_claims_and_errors():
    base = dict(mode="baseline", resolved=False, regression=False, claimed_done=False, false_acceptance=False,
                counterexamples=0, tool_calls=0, tokens=0, patch_lines=0, seconds=0.0, error="")
    table = summarize([base, dict(base, error="Boom: x")])
    assert "n/a" in table and "1 run(s) crashed" in table
    assert summarize([]).startswith("| mode |")
