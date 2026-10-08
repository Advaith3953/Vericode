"""Self-falsification: ask the model to write tests that would prove its own patch wrong."""
from __future__ import annotations

import re

from .prompts import falsify_prompt


def extract_python_block(text: str):
    m = re.search(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.S)
    if m:
        return m.group(1).strip() or None
    return text.strip() if "def test_" in text else None


def generate_adversarial_tests(llm, issue: str, ws, n: int, traj):
    sources = "\n\n".join(f"### {p}\n{c}" for p, c in ws.changed_source_files().items()) or "(none)"
    prompt = falsify_prompt(issue, ws.diff(), sources, ws.list_files(), n)
    resp = llm.chat([
        {"role": "system", "content": "You write rigorous, minimal pytest tests."},
        {"role": "user", "content": prompt},
    ])
    traj.record_llm(resp)
    code = extract_python_block(resp.text)
    traj.log("falsify_request", has_code=code is not None)
    return code
