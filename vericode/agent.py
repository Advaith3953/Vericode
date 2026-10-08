"""Tool-using agent loop with an optional self-falsification phase."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .falsify import generate_adversarial_tests
from .prompts import system_prompt, user_prompt
from .tools import Workspace
from .trajectory import Trajectory


@dataclass
class AgentConfig:
    max_steps: int = 25          # tool-call budget shared by the whole run
    verify: bool = False         # enable self-falsification
    max_rounds: int = 2          # maximum challenge rounds
    adversarial_tests: int = 5   # tests requested per round


@dataclass
class RunResult:
    claimed_done: bool
    summary: str
    rounds: int              # challenge rounds that sent feedback to the agent
    counterexamples: int     # adversarial tests that failed against the patch
    steps_used: int


def parse_action(text: str):
    """Return the first JSON object containing a string `tool` field, or None."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            return obj
    return None


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n // 2] + "\n...[truncated]...\n" + s[-n // 2:]


class Agent:
    def __init__(self, llm, workspace: Workspace, config: AgentConfig | None = None, traj: Trajectory | None = None):
        self.llm, self.ws = llm, workspace
        self.cfg = config or AgentConfig()
        self.traj = traj or Trajectory()
        self.steps_used = 0
        self.summary = ""
        self.issue = ""

    # ----- core tool loop; returns True if the agent called finish -----
    def _loop(self, messages: list[dict]) -> bool:
        while self.steps_used < self.cfg.max_steps:
            resp = self.llm.chat(messages)
            self.traj.record_llm(resp)
            messages.append({"role": "assistant", "content": resp.text})
            self.steps_used += 1
            action = parse_action(resp.text)
            if action is None:
                obs = 'ERROR: reply with a single JSON object: {"thought": "...", "tool": "...", "args": {...}}'
                self.traj.log("format_error", text=_trunc(resp.text, 300))
            else:
                tool, args = action["tool"], action.get("args") or {}
                if not isinstance(args, dict):
                    args = {}
                if tool == "finish":
                    self.summary = str(args.get("summary", ""))
                    self.traj.log("finish", summary=self.summary)
                    return True
                obs = self.ws.call(tool, args)
                self.traj.tool_calls += 1
                self.traj.log("tool", tool=tool, args=_trunc(json.dumps(args), 600), observation=_trunc(obs, 1500))
            messages.append({"role": "user", "content": "OBSERVATION:\n" + _trunc(obs, 4000)})
        return False

    # ----- one challenge round: returns (n_counterexamples, feedback) or None to accept -----
    def _challenge(self, r: int):
        suite = self.ws.run_pytest()
        if not suite.ok:
            self.traj.log("verify", round=r, result="suite_failing", detail=suite.summary())
            return 0, "You called finish, but the test suite is not passing:\n" + suite.tail() + "\nKeep working."
        code = generate_adversarial_tests(self.llm, self.issue, self.ws, self.cfg.adversarial_tests, self.traj)
        if not code:
            self.traj.log("verify", round=r, result="no_tests_generated")
            return None
        rel = self.ws.write_test(f"r{r}", code)
        alone = self.ws.run_pytest([rel])
        if alone.timed_out or alone.collection_error or alone.passed + alone.failed == 0:
            self.ws.remove(rel)  # broken test file: not evidence against the patch
            self.traj.log("verify", round=r, result="invalid_tests_discarded")
            return None
        if alone.ok:
            self.traj.log("verify", round=r, result="all_adversarial_pass", n=alone.passed)
            return None
        n = alone.failed
        self.traj.log("verify", round=r, result="counterexamples", n=n, failed=sorted(alone.failed_ids))
        return n, (
            f"Adversarial tests derived from the issue found {n} failing case(s) against your patch:\n"
            f"{alone.tail()}\n\nIf a test is correct per the issue, fix the code. If a test contradicts the "
            f"issue, you may correct it or remove it with rollback('{rel}') -- only that file. "
            "Then run the full suite and call finish again."
        )

    def run(self, issue: str) -> RunResult:
        self.issue = issue
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_prompt(issue, self.ws.list_files())},
        ]
        claimed = self._loop(messages)
        rounds = counter = 0
        if self.cfg.verify and claimed:
            for r in range(1, self.cfg.max_rounds + 1):
                result = self._challenge(r)
                if result is None:
                    break
                n, feedback = result
                counter += n
                rounds += 1
                messages.append({"role": "user", "content": feedback})
                claimed = self._loop(messages)
                if not claimed:
                    break
        return RunResult(claimed, self.summary, rounds, counter, self.steps_used)
