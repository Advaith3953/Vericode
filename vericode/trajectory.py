"""Step-by-step run log. This is the raw experimental data."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Trajectory:
    steps: list = field(default_factory=list)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: int = 0
    started: float = field(default_factory=time.time)

    def log(self, kind: str, **data) -> None:
        self.steps.append({"i": len(self.steps) + 1, "t": round(time.time() - self.started, 3), "kind": kind, **data})

    def record_llm(self, resp) -> None:
        self.llm_calls += 1
        self.prompt_tokens += resp.prompt_tokens
        self.completion_tokens += resp.completion_tokens

    @property
    def elapsed(self) -> float:
        return round(time.time() - self.started, 3)

    def save(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "llm_calls": self.llm_calls, "tool_calls": self.tool_calls,
            "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
            "elapsed": self.elapsed, "steps": self.steps,
        }, indent=2))
