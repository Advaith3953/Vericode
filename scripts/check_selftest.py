"""Fail loudly if the mock-model benchmark runs do not behave as they must.

oracle (applies the reference fix) must resolve every case; noop (does nothing, claims done) must resolve none
and be caught by the hidden tests every time. If either is violated the harness cannot be trusted.
"""
import json
import sys
from pathlib import Path


def rows(d):
    return [json.loads(x) for x in (Path(d) / "results.jsonl").read_text().splitlines() if x.strip()]


def main(oracle_dir, noop_dir):
    problems = []
    o, n = rows(oracle_dir), rows(noop_dir)
    if not o or not n:
        problems.append("no result rows")
    problems += [f"oracle failed {r['case']}/{r['mode']}: {r['error'] or 'unresolved'}" for r in o if not r["resolved"]]
    problems += [f"noop wrongly resolved {r['case']}/{r['mode']}" for r in n if r["resolved"]]
    problems += [f"noop not caught by hidden tests {r['case']}/{r['mode']}" for r in n
                 if r["claimed_done"] and not r["false_acceptance"]]
    if problems:
        print("SELFTEST FAILED:\n  " + "\n  ".join(problems))
        return 1
    print(f"selftest ok: oracle resolved {len(o)}/{len(o)}, noop resolved 0/{len(n)} and was caught every time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:3]))
