import json
import shutil
from pathlib import Path

from vericode.agent import Agent, AgentConfig
from vericode.llm import ScriptedLLM
from vericode.tools import Workspace

CASE = Path(__file__).parent.parent / "bench" / "bugs" / "bug01_pagination"
ISSUE = (CASE / "issue.md").read_text()


def act(tool, **args):
    return json.dumps({"thought": "t", "tool": tool, "args": args})


PARTIAL = act("edit_file", path="pagination.py", old="page * per_page", new="(page - 1) * per_page")
FULL = act("write_file", path="pagination.py", content=(CASE / "fix" / "pagination.py").read_text())
ADV_FAILS = "```python\nimport pytest\nfrom pagination import paginate\n\ndef test_page_zero_invalid():\n    with pytest.raises(ValueError):\n        paginate([1, 2], 0, 1)\n```"
ADV_PASSES = "```python\nfrom pagination import paginate\n\ndef test_ok():\n    assert paginate([1, 2, 3], 2, 1) == [2]\n```"


def test_verified_agent_revises_after_counterexample():
    ws = Workspace(CASE / "repo")
    llm = ScriptedLLM([
        PARTIAL, act("run_tests"), act("finish", summary="done"),   # incomplete fix, claims done
        ADV_FAILS,                                                   # falsifier finds a counterexample
        FULL, act("finish", summary="done again"),                   # agent revises
        ADV_PASSES,                                                  # second challenge passes
    ])
    res = Agent(llm, ws, AgentConfig(verify=True)).run(ISSUE)
    assert res.claimed_done and res.rounds == 1 and res.counterexamples == 1
    assert ws.run_pytest().ok
    shutil.rmtree(ws.root, ignore_errors=True)


def test_baseline_accepts_incomplete_patch():
    ws = Workspace(CASE / "repo")
    llm = ScriptedLLM([PARTIAL, act("finish", summary="done")])
    res = Agent(llm, ws, AgentConfig(verify=False)).run(ISSUE)
    assert res.claimed_done and res.rounds == 0 and res.counterexamples == 0
    shutil.rmtree(ws.root, ignore_errors=True)


def test_format_errors_consume_budget_and_do_not_crash():
    ws = Workspace(CASE / "repo")
    res = Agent(ScriptedLLM(["blah"] * 5), ws, AgentConfig(max_steps=3)).run(ISSUE)
    assert not res.claimed_done and res.steps_used == 3
    shutil.rmtree(ws.root, ignore_errors=True)


def test_broken_adversarial_file_is_discarded_not_counted():
    ws = Workspace(CASE / "repo")
    llm = ScriptedLLM([FULL, act("finish", summary="done"), "```python\nthis is not python(\n```"])
    res = Agent(llm, ws, AgentConfig(verify=True)).run(ISSUE)
    assert res.counterexamples == 0 and res.rounds == 0
    assert "test_adv_" not in ws.list_files()
    shutil.rmtree(ws.root, ignore_errors=True)
