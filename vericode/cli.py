"""Command line: run the agent on a repository + issue."""
from __future__ import annotations

import argparse
from pathlib import Path

from .agent import Agent, AgentConfig
from .llm import make_llm
from .tools import Workspace
from .trajectory import Trajectory


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="vericode")
    ap.add_argument("--repo", required=True, help="path to the repository (it is copied, never modified)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--issue")
    g.add_argument("--issue-file")
    ap.add_argument("--llm", default="ollama:llama3.1:8b")
    ap.add_argument("--verify", action="store_true", help="enable self-falsification")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--traj-out", default="trajectory.json")
    ap.add_argument("--patch-out", default="patch.diff")
    a = ap.parse_args(argv)

    issue = a.issue or Path(a.issue_file).read_text()
    ws, traj = Workspace(a.repo), Trajectory()
    cfg = AgentConfig(max_steps=a.max_steps, verify=a.verify, max_rounds=a.rounds)
    try:
        try:
            res = Agent(make_llm(a.llm), ws, cfg, traj).run(issue)
        except OSError as e:  # URLError is an OSError: model server not reachable
            print(f"Could not reach the model server ({e}). Is `ollama serve` running and the model pulled?")
            return 2
        traj.save(a.traj_out)
        Path(a.patch_out).write_text(ws.patch_text() + "\n")
        final = ws.run_pytest()
        print(f"claimed_done={res.claimed_done} rounds={res.rounds} counterexamples={res.counterexamples} "
              f"steps={res.steps_used} tests: {final.summary()}")
        print(f"patch -> {a.patch_out}   trajectory -> {a.traj_out}")
        return 0 if final.ok else 1
    finally:
        ws.cleanup()  # the working copy is temporary; the patch file is the deliverable


if __name__ == "__main__":
    raise SystemExit(main())
