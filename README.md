# VeriCode: a coding agent that tries to prove its own patch wrong

> New here? Read [`WALKTHROUGH.md`](WALKTHROUGH.md) for a guided tour, expected outputs and how to add bug cases.

Question this project answers with data: **does making an agent attack its own patch improve results over a plain agent?**

```
issue -> agent (tools) -> patch -> finish
                                     |
              [verified mode]  run suite -> model writes adversarial tests from the ISSUE
                                     |          |
                                     |      any fail? -> feedback -> agent revises (max N rounds)
                                     v
                                  accept
```

## Quick start
```bash
pip install -e .[dev]
python -m pytest                      # 79 tests: every tool, parsing, agent loop, CLI, Ollama client, harness, integrity regressions
make check                            # lint + types + tests with a 90 % coverage gate + mock-model benchmark selftest
ollama pull llama3.1:8b               # or any local model

# fix an issue in a repo (the repo is copied, never modified)
vericode --repo path/to/repo --issue-file issue.md --verify --llm ollama:llama3.1:8b

# controlled benchmark: baseline vs verified, 3 seeds, 5 seeded bugs
python -m bench.harness --llm ollama:llama3.1:8b --seeds 3 --out results/run1
```
Outputs: `results.jsonl` (one row per run), `summary.md` (table), `trajectories/*.json` (every step).

## Design decisions
- **Hidden tests.** Each bug has a `hidden/` suite the agent never sees. "Resolved" means the hidden suite passes, so the agent cannot win by overfitting visible tests.
- **Read-only original tests.** The agent cannot delete or weaken existing tests, and it cannot create or edit files that change how pytest runs (`conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `sitecustomize.py`).
- **Tamper-proof scoring.** Pass/fail counts come from pytest's own junit-xml report, not from scraping its text output, so a test that prints "99 passed" cannot change the numbers.
- **Falsifier sees the issue, not just the code.** Tests are derived from the issue text, which reduces tests that merely confirm the implementation.
- **Broken adversarial files are discarded**, not counted as counterexamples.
- **Same model, seed, step budget and sandbox for both arms.** The only difference is the verification phase.
- **Metrics:** resolved rate, regression rate, false-acceptance rate (claimed done but hidden tests fail), counterexamples found, tool calls, tokens, patch size, time.

## Known limitations
- A counterexample can come from a *wrong* test. The count is therefore an upper bound on real defects found; the hidden suite is the ground truth.
- The last revision after the final round is not re-challenged.
- Only 5 small seeded bugs ship here. Add more (different bug classes, multi-file repos) before drawing conclusions, and run several seeds: small local models are noisy.
- Mock backends (`mock:oracle`, `mock:noop`) only validate the pipeline. They say nothing about model quality.
- The workspace is a temp-directory copy, **not** a security sandbox: agent-written code runs as a normal subprocess with your user's permissions and network access. Use a container if you run untrusted models.
- Only the protections above are enforced. An agent can still edit non-test source files in ways that interfere with pytest; the hidden suite remains the ground truth.

## Layout
```
vericode/   agent.py (loop + challenge), tools.py (sandbox), falsify.py, llm.py, prompts.py, trajectory.py, cli.py
bench/      harness.py, bugs/<case>/{issue.md, repo/, hidden/, fix/}
tests/      tests for the project itself
```
`fix/` holds the reference solution and is used only by the mock oracle, never shown to a model.

## Next steps
1. Run the benchmark on your local model (3+ seeds) and read the failing trajectories.
2. Add 15-25 more bugs: concurrency, DB transactions, API error handling, multi-file.
3. Ablations: rounds 0/1/2/3, tests per round, with/without issue text given to the falsifier.
4. Write up results with the limitations above.
