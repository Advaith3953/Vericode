import pytest

from bench.harness import BUGS, load_fixes, run_case
from vericode.agent import AgentConfig
from vericode.llm import make_llm

CASES = sorted(c for c in BUGS.iterdir() if c.is_dir())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
@pytest.mark.parametrize("mode", ["baseline", "verified"])
def test_oracle_resolves_every_seeded_bug(case, mode):
    row = run_case(case, mode, make_llm("mock:oracle", fixes=load_fixes(case)),
                   AgentConfig(verify=(mode == "verified")))
    assert row["error"] is None
    assert row["resolved"] and not row["regression"] and not row["false_acceptance"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_noop_is_a_false_acceptance(case):
    row = run_case(case, "baseline", make_llm("mock:noop"), AgentConfig())
    assert row["claimed_done"] and not row["resolved"] and row["false_acceptance"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_seeded_bug_is_visible_but_not_fully_covered_by_visible_tests(case):
    """Sanity: visible suite fails on the buggy repo (so the issue is reproducible)."""
    import shutil

    from vericode.tools import Workspace
    ws = Workspace(case / "repo")
    res = ws.run_pytest()
    shutil.rmtree(ws.root, ignore_errors=True)
    assert res.failed >= 1 and res.passed >= 0
