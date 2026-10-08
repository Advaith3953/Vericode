"""Controlled comparison: baseline agent vs self-verifying agent on seeded bugs.

    python -m bench.harness --llm ollama:llama3.1:8b --seeds 3 --out results/run1
    python -m bench.harness --llm mock:oracle --out results/selftest   # pipeline check, no model

Per run it records whether the HIDDEN tests pass (the agent never sees them),
whether any originally-passing visible test regressed, and whether the agent
claimed success when it was wrong (false acceptance).
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from vericode.agent import Agent, AgentConfig
from vericode.llm import make_llm
from vericode.tools import Workspace, run_pytest
from vericode.trajectory import Trajectory

BUGS = Path(__file__).parent / "bugs"


def load_fixes(case: Path) -> dict[str, str]:
    fix = case / "fix"
    return {p.relative_to(fix).as_posix(): p.read_text() for p in fix.rglob("*.py")}


def run_case(case: Path, mode: str, llm, cfg: AgentConfig, traj_dir: Path | None = None, seed: int = 0) -> dict:
    ws = Workspace(case / "repo")
    p0 = ws.run_pytest().passed_ids  # tests passing before the agent touches anything
    traj = Trajectory()
    row = {"case": case.name, "mode": mode, "seed": seed, "error": None}
    try:
        res = Agent(llm, ws, cfg, traj).run((case / "issue.md").read_text())
        orig_tests = sorted(p for p in ws.protected if p.startswith("tests/") and p.endswith(".py"))
        after = ws.run_pytest(orig_tests).passed_ids
        sandbox = Path(tempfile.mkdtemp(prefix="vericode_eval_"))
        try:
            shutil.copytree(ws.root, sandbox / "w")
            shutil.copytree(case / "hidden", sandbox / "w" / "hidden_tests")
            hidden = run_pytest(sandbox / "w", ["hidden_tests"])
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        resolved = hidden.ok and hidden.failed == 0
        row.update(
            resolved=resolved, regression=bool(p0 - after), claimed_done=res.claimed_done,
            false_acceptance=res.claimed_done and not resolved, counterexamples=res.counterexamples,
            rounds=res.rounds, llm_calls=traj.llm_calls, tool_calls=traj.tool_calls,
            tokens=traj.prompt_tokens + traj.completion_tokens, patch_lines=ws.patch_lines(),
            seconds=traj.elapsed,
        )
    except Exception as e:  # noqa: BLE001 - a crashed run is a data point, not a harness crash
        row.update(error=f"{type(e).__name__}: {e}", resolved=False, regression=False, claimed_done=False,
                   false_acceptance=False, counterexamples=0, rounds=0, llm_calls=traj.llm_calls,
                   tool_calls=traj.tool_calls, tokens=0, patch_lines=0, seconds=traj.elapsed)
    finally:
        if traj_dir:
            traj.save(traj_dir / f"{case.name}__{mode}__s{seed}.json")
        shutil.rmtree(ws.root, ignore_errors=True)
    return row


def summarize(rows: list[dict]) -> str:
    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    lines = ["| mode | runs | resolved | regression | false-accept | counterexamples | tool calls | tokens | patch lines | sec |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for mode in sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if r["mode"] == mode]
        claimed = [r for r in rs if r["claimed_done"]]
        fa = f"{100 * mean([r['false_acceptance'] for r in claimed]):.0f}%" if claimed else "n/a"
        lines.append(
            f"| {mode} | {len(rs)} | {100 * mean([r['resolved'] for r in rs]):.0f}% | "
            f"{100 * mean([r['regression'] for r in rs]):.0f}% | {fa} | "
            f"{mean([r['counterexamples'] for r in rs]):.2f} | {mean([r['tool_calls'] for r in rs]):.1f} | "
            f"{mean([r['tokens'] for r in rs]):.0f} | {mean([r['patch_lines'] for r in rs]):.1f} | "
            f"{mean([r['seconds'] for r in rs]):.1f} |")
    lines.append("\nfalse-accept = share of runs that claimed done where the hidden tests still fail.")
    errs = [r for r in rows if r["error"]]
    if errs:
        lines.append(f"\n{len(errs)} run(s) crashed (counted as unresolved); see results.jsonl.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.harness")
    ap.add_argument("--llm", default="ollama:llama3.1:8b")
    ap.add_argument("--modes", default="baseline,verified")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--cases", default="", help="comma-separated substrings to select cases")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default="results/run")
    ap.add_argument("--bugs-dir", default=str(BUGS), help="directory holding the bug cases (default: bench/bugs)")
    a = ap.parse_args(argv)
    bugs = Path(a.bugs_dir)
    if not bugs.is_dir():
        ap.error(f"bug directory {bugs} not found. Run from a source checkout (pip install -e .) or pass --bugs-dir.")

    out = Path(a.out)
    (out / "trajectories").mkdir(parents=True, exist_ok=True)
    wanted = [s for s in a.cases.split(",") if s]
    cases = [c for c in sorted(bugs.iterdir()) if c.is_dir() and (not wanted or any(w in c.name for w in wanted))]
    rows = []
    for case in cases:
        for mode in a.modes.split(","):
            for seed in range(a.seeds):
                cfg = AgentConfig(max_steps=a.max_steps, verify=(mode == "verified"), max_rounds=a.rounds)
                llm = make_llm(a.llm, seed=seed, fixes=load_fixes(case))
                row = run_case(case, mode, llm, cfg, out / "trajectories", seed)
                rows.append(row)
                print(f"{case.name:22s} {mode:9s} s{seed} resolved={row['resolved']} "
                      f"counterexamples={row['counterexamples']} err={row['error']}")
    (out / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    table = summarize(rows)
    (out / "summary.md").write_text(table + "\n")
    print("\n" + table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
