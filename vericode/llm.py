"""LLM backends. The agent only needs `chat(messages) -> LLMResponse`."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .prompts import FALSIFY_MARKER


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLM:
    def chat(self, messages: list[dict]) -> LLMResponse:  # pragma: no cover - interface
        raise NotImplementedError


class OllamaLLM(LLM):
    """Local model served by Ollama (http://localhost:11434)."""

    def __init__(self, model="llama3.1:8b", host="http://localhost:11434",
                 temperature=0.2, seed=0, timeout=600):
        self.model, self.host, self.temperature, self.seed, self.timeout = model, host, temperature, seed, timeout

    def chat(self, messages):
        body = json.dumps({
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed},
        }).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        return LLMResponse(data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0))


class ScriptedLLM(LLM):
    """Replays fixed responses (str or callable(messages)->str). Used in tests."""

    def __init__(self, responses):
        self.responses, self.i = list(responses), 0

    def chat(self, messages):
        if self.i >= len(self.responses):
            return LLMResponse(json.dumps({"tool": "finish", "args": {"summary": "script exhausted"}}))
        r = self.responses[self.i]
        self.i += 1
        return LLMResponse(r(messages) if callable(r) else r)


class MockLLM(LLM):
    """Deterministic stand-in used to validate the pipeline without a model.

    kind="oracle": writes the reference fix, runs tests, finishes.
    kind="noop":   finishes immediately without changing anything.
    """

    def __init__(self, kind: str, fixes: dict[str, str] | None = None):
        self.kind, self.fixes = kind, fixes or {}

    def _script(self) -> list[dict]:
        if self.kind == "noop":
            return [{"tool": "finish", "args": {"summary": "nothing to do"}}]
        acts = [{"tool": "write_file", "args": {"path": p, "content": c}} for p, c in self.fixes.items()]
        return acts + [{"tool": "run_tests", "args": {}}, {"tool": "finish", "args": {"summary": "fixed"}}]

    def chat(self, messages):
        if FALSIFY_MARKER in messages[-1]["content"]:
            return LLMResponse("```python\ndef test_adv_placeholder():\n    assert True\n```")
        n = sum(1 for m in messages if m["role"] == "assistant")
        script = self._script()
        act = script[n] if n < len(script) else {"tool": "finish", "args": {"summary": "done"}}
        return LLMResponse(json.dumps(act))


def make_llm(spec: str, seed: int = 0, fixes: dict[str, str] | None = None) -> LLM:
    """spec: 'ollama:<model>' | 'mock:oracle' | 'mock:noop'"""
    kind, _, arg = spec.partition(":")
    if kind == "ollama":
        return OllamaLLM(model=arg or "llama3.1:8b", seed=seed)
    if kind == "mock":
        return MockLLM(arg or "noop", fixes)
    raise ValueError(f"unknown llm spec: {spec}")
