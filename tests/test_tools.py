import json as _json
import shutil
from pathlib import Path

import pytest

from bench.harness import BUGS as _BUGS
from bench.harness import run_case as _run_case
from vericode.agent import AgentConfig as _AgentConfig
from vericode.llm import ScriptedLLM as _ScriptedLLM
from vericode.tools import Workspace

CASE = Path(__file__).parent.parent / "bench" / "bugs" / "bug01_pagination" / "repo"


@pytest.fixture
def ws():
    w = Workspace(CASE)
    yield w
    shutil.rmtree(w.root, ignore_errors=True)


def test_path_escape_blocked(ws):
    assert ws.call("read_file", {"path": "../../etc/passwd"}).startswith("ERROR")
    assert ws.call("write_file", {"path": "/tmp/x", "content": "x"}).startswith("ERROR")


def test_original_tests_are_read_only(ws):
    assert "read-only" in ws.call("write_file", {"path": "tests/test_pagination.py", "content": ""})
    assert "read-only" in ws.call("edit_file", {"path": "tests/test_pagination.py", "old": "paginate", "new": "x"})
    assert "read-only" in ws.call("rollback", {"path": "tests/test_pagination.py"})


def test_edit_requires_unique_match(ws):
    assert "matches" in ws.call("edit_file", {"path": "pagination.py", "old": "per_page", "new": "pp"})
    assert ws.call("edit_file", {"path": "pagination.py", "old": "page * per_page", "new": "(page - 1) * per_page"}) \
        == "edited pagination.py"


def test_diff_patch_lines_and_rollback(ws):
    assert ws.diff() == "(no changes)"
    ws.call("edit_file", {"path": "pagination.py", "old": "page * per_page", "new": "(page - 1) * per_page"})
    assert "(page - 1)" in ws.diff() and ws.patch_lines() == 2
    ws.call("rollback", {})
    assert ws.diff() == "(no changes)"


def test_new_test_files_are_tracked_and_removable(ws):
    ws.call("create_test", {"name": "x", "code": "def test_a():\n    assert True\n"})
    assert "tests/test_adv_x.py" in ws.list_files()
    assert ws.patch_lines() == 0  # tests do not count toward patch size
    ws.call("rollback", {"path": "tests/test_adv_x.py"})
    assert "test_adv_x" not in ws.list_files()


def test_run_tests_reports_ids(ws):
    res = ws.run_pytest()
    assert res.failed == 1 and res.passed == 1 and not res.ok
    assert any("test_first_page" in i for i in res.failed_ids)


def test_unknown_tool_and_bad_args(ws):
    assert "unknown tool" in ws.call("rm_rf", {})
    assert "bad arguments" in ws.call("read_file", {"nope": 1})


# ---------------------------------------------------------------- regression tests (review fixes)


def _fresh_ws():
    return Workspace(_BUGS / "bug01_pagination" / "repo")


@pytest.mark.parametrize("name", ["conftest.py", "tests/conftest.py", "pytest.ini", "tox.ini", "setup.cfg",
                                  "pyproject.toml", "sitecustomize.py"])
def test_agent_cannot_create_pytest_control_files(name):
    w = _fresh_ws()
    try:
        out = w.call("write_file", {"path": name, "content": "x = 1\n"})
        assert out.startswith("ERROR") and not (w.root / name).exists()
    finally:
        w.cleanup()


def test_conftest_cheat_no_longer_resolves_bug():
    """Regression: a conftest.py that rewrites every failure to 'passed' used to score as resolved."""
    cheat = ("import pytest\n@pytest.hookimpl(hookwrapper=True)\n"
             "def pytest_runtest_makereport(item, call):\n    out = yield\n"
             "    r = out.get_result()\n    if r.failed:\n        r.outcome = 'passed'\n")
    act = lambda t, **a: _json.dumps({"tool": t, "args": a})  # noqa: E731
    llm = _ScriptedLLM([act("write_file", path="conftest.py", content=cheat), act("finish", summary="done")])
    row = _run_case(_BUGS / "bug01_pagination", "baseline", llm, _AgentConfig())
    assert row["resolved"] is False and row["false_acceptance"] is True


def test_test_output_cannot_forge_result_counts():
    """Regression: a test that prints '99 passed' used to change the parsed counts."""
    w = _fresh_ws()
    try:
        w.write_test("spoof", "def test_x():\n    print('99 passed 7 errors 3 failed')\n    assert False\n")
        r = w.run_pytest(["tests/test_adv_spoof.py"])
        assert (r.passed, r.failed, r.errors) == (0, 1, 0) and not r.ok
    finally:
        w.cleanup()


def test_syntax_error_file_is_a_collection_error():
    w = _fresh_ws()
    try:
        w.write_test("broken", "this is not python(\n")
        assert w.run_pytest(["tests/test_adv_broken.py"]).collection_error
    finally:
        w.cleanup()


def test_cli_removes_its_temp_workspace(tmp_path, monkeypatch):
    import glob
    import tempfile

    from vericode import cli
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    rc = cli.main(["--repo", str(_BUGS / "bug01_pagination" / "repo"), "--issue", "x", "--llm", "mock:noop",
                   "--traj-out", str(tmp_path / "t.json"), "--patch-out", str(tmp_path / "p.diff")])
    assert rc == 1
    assert glob.glob(str(tmp_path / "vericode_ws_*")) == []
