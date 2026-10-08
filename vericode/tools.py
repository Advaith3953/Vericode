"""Sandboxed workspace and the tools the agent can call.

Integrity rules:
  * every path is confined to the workspace root;
  * test files that existed originally are read-only (the agent cannot make
    the suite green by weakening or deleting tests);
  * hidden evaluation tests never live in the workspace.
"""
from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.pyc")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
MAX_READ_LINES = 400
# Files that can change how pytest discovers, selects, reports or hooks tests. The agent may never
# create or modify them: a new conftest.py could turn every failure into a pass.
PYTEST_CONTROL_FILES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml",
                        "sitecustomize.py", "usercustomize.py"}


class ToolError(Exception):
    pass


@dataclass
class PytestResult:
    returncode: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    passed_ids: set = field(default_factory=set)
    failed_ids: set = field(default_factory=set)
    output: str = ""
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.passed > 0

    @property
    def collection_error(self) -> bool:
        return self.errors > 0 and self.passed == 0 and self.failed == 0

    def tail(self, n: int = 3500) -> str:
        return self.output[-n:]

    def summary(self) -> str:
        if self.timed_out:
            return "TIMEOUT"
        return f"{self.passed} passed, {self.failed} failed, {self.errors} errors"


def _parse_junit(xml_path: Path, res: PytestResult) -> None:
    """Fill counts/ids from pytest's junit report. This file is written by pytest itself, so test
    output (print statements, captured logs) cannot forge the numbers the way text scraping could."""
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return
    for tc in root.iter("testcase"):
        tid = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        kinds = {child.tag for child in tc}
        if "failure" in kinds:
            res.failed += 1
            res.failed_ids.add(tid)
        elif "error" in kinds:
            res.errors += 1
            res.failed_ids.add(tid)
        elif "skipped" in kinds:
            continue
        else:
            res.passed += 1
            res.passed_ids.add(tid)


def run_pytest(root: Path, paths=None, timeout: int = 60) -> PytestResult:
    with tempfile.TemporaryDirectory(prefix="vericode_junit_") as td:
        xml_path = Path(td) / "report.xml"
        cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
               "--tb=short", f"--junitxml={xml_path}", *(paths or [])]
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
        env.update({"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            partial = e.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            return PytestResult(returncode=-1, output=partial, timed_out=True)
        res = PytestResult(p.returncode, output=p.stdout + p.stderr)
        _parse_junit(xml_path, res)
        return res


class Workspace:
    TOOL_NAMES = ["list_files", "read_file", "search_code", "edit_file", "write_file",
                  "create_test", "run_tests", "diff", "rollback"]

    def __init__(self, src, root=None):
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="vericode_ws_"))
        shutil.copytree(src, self.root, ignore=IGNORE, dirs_exist_ok=True)
        self.root = self.root.resolve()
        self.snapshot = self._read_all()
        self.protected = {p for p in self.snapshot if self._is_test_path(p)}

    def cleanup(self) -> None:
        """Delete the temporary working copy."""
        shutil.rmtree(self.root, ignore_errors=True)

    # ---------- helpers ----------
    @staticmethod
    def _is_test_path(rel: str) -> bool:
        p = Path(rel)
        return p.parts[0] == "tests" or p.name.startswith("test_") or p.name == "conftest.py"

    def _read_all(self) -> dict[str, str]:
        out = {}
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not (set(p.relative_to(self.root).parts) & SKIP_PARTS):
                try:
                    out[p.relative_to(self.root).as_posix()] = p.read_text()
                except UnicodeDecodeError:
                    pass
        return out

    def _resolve(self, rel) -> Path:
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            raise ToolError("path must be a non-empty path relative to the repo root")
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise ToolError("path escapes the repository")
        return p

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def _check_writable(self, rel: str) -> None:
        if Path(rel).name in PYTEST_CONTROL_FILES:
            raise ToolError(f"{Path(rel).name} controls how tests run and cannot be created or modified")
        if rel in self.protected:
            raise ToolError(f"{rel} is an original test file and is read-only")
        if rel.startswith(".git"):
            raise ToolError("cannot write inside .git")

    # ---------- tools (return text) ----------
    def list_files(self) -> str:
        return "\n".join(self._read_all().keys()) or "(empty)"

    def read_file(self, path, start=1, end=None) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"{path} does not exist")
        lines = p.read_text(encoding="utf-8").splitlines()
        start = max(1, int(start))
        end = min(len(lines), int(end)) if end else len(lines)
        end = min(end, start + MAX_READ_LINES - 1)
        return "\n".join(f"{n:4d} | {lines[n - 1]}" for n in range(start, end + 1)) or "(empty file)"

    def search_code(self, pattern, glob="*.py") -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"bad regex: {e}") from e
        hits = []
        for rel, text in self._read_all().items():
            if not fnmatch.fnmatch(Path(rel).name, glob):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()}")
        return "\n".join(hits[:50]) or "(no matches)"

    def edit_file(self, path, old, new) -> str:
        p = self._resolve(path)
        rel = self._rel(p)
        self._check_writable(rel)
        if not p.is_file():
            raise ToolError(f"{path} does not exist")
        if not old:
            raise ToolError("`old` must be non-empty")
        text = p.read_text()
        n = text.count(old)
        if n == 0:
            raise ToolError("`old` text not found (it must match exactly, including whitespace)")
        if n > 1:
            raise ToolError(f"`old` matches {n} places; include more surrounding context")
        p.write_text(text.replace(old, new, 1))
        return f"edited {rel}"

    def write_file(self, path, content) -> str:
        p = self._resolve(path)
        rel = self._rel(p)
        self._check_writable(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {rel} ({len(content.splitlines())} lines)"

    def write_test(self, name: str, code: str) -> str:
        """Create tests/test_adv_<name>.py; returns its relative path."""
        name = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
        rel = f"tests/test_adv_{name}.py"
        self._check_writable(rel)
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / rel).write_text(code if code.endswith("\n") else code + "\n")
        return rel

    def create_test(self, name, code) -> str:
        return f"created {self.write_test(name, code)}"

    def remove(self, rel: str) -> None:
        self._check_writable(rel)
        p = self._resolve(rel)
        if p.exists():
            p.unlink()

    def run_pytest(self, paths=None, timeout: int = 60) -> PytestResult:
        return run_pytest(self.root, paths, timeout)

    def run_tests(self, path=None) -> str:
        res = self.run_pytest([path] if path else None)
        return f"{res.summary()}\n{res.tail()}"

    def patch_text(self) -> str:
        now = self._read_all()
        chunks = []
        for rel in sorted(set(self.snapshot) | set(now)):
            old, new = self.snapshot.get(rel), now.get(rel)
            if old == new:
                continue
            chunks.append("\n".join(difflib.unified_diff(
                (old or "").splitlines(), (new or "").splitlines(),
                fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="")))
        return "\n".join(chunks)

    def diff(self) -> str:
        return self.patch_text() or "(no changes)"

    def patch_lines(self) -> int:
        """Added+removed lines in non-test files."""
        now = self._read_all()
        total = 0
        for rel in set(self.snapshot) | set(now):
            if self._is_test_path(rel) or self.snapshot.get(rel) == now.get(rel):
                continue
            for line in difflib.unified_diff((self.snapshot.get(rel) or "").splitlines(),
                                             (now.get(rel) or "").splitlines(), lineterm=""):
                if line[:1] in "+-" and not line.startswith(("+++", "---")):
                    total += 1
        return total

    def changed_source_files(self) -> dict[str, str]:
        now = self._read_all()
        return {r: t for r, t in now.items() if not self._is_test_path(r) and self.snapshot.get(r) != t}

    def rollback(self, path=None) -> str:
        if path:
            p = self._resolve(path)
            rel = self._rel(p)
            self._check_writable(rel)
            if rel in self.snapshot:
                p.write_text(self.snapshot[rel])
                return f"restored {rel}"
            if p.exists():
                p.unlink()
                return f"deleted {rel}"
            raise ToolError(f"{path} does not exist")
        for rel, text in self.snapshot.items():
            (self.root / rel).write_text(text)
        for rel in set(self._read_all()) - set(self.snapshot):
            (self.root / rel).unlink()
        return "restored all files to their original state"

    # ---------- dispatch ----------
    def call(self, name: str, args: dict) -> str:
        if name not in self.TOOL_NAMES:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.TOOL_NAMES + ['finish'])}"
        try:
            return str(getattr(self, name)(**args))
        except ToolError as e:
            return f"ERROR: {e}"
        except TypeError as e:
            return f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:  # noqa: BLE001 - surface any tool failure to the model
            return f"ERROR: {type(e).__name__}: {e}"
