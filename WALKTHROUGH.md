# VeriCode walkthrough

A guided tour: what the project does, how to prove it works on your machine in five minutes, how to read the
code, and how to extend it. The README is the reference; this file is the "show me" version.

## 1. The idea in one picture

```
issue ──► agent (tools) ──► patch ──► finish
                                        │
             verified mode only:        ▼
             run the visible suite ─ failing? ─► tell the agent, keep working
                                        │ passing
                                        ▼
             model writes adversarial tests from the ISSUE text (not from the code)
                                        │
                  any fail? ──yes──► feedback ──► agent revises (up to --rounds times)
                                        │ no
                                        ▼
                                     accept
```

The research question: **does making an agent attack its own patch beat a plain agent?** Everything else in
the repo exists so that the answer is measured honestly: hidden tests, read-only tests, identical budgets for
both arms.

## 2. Install and prove it works (no model needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest                 # expect: 79 passed (about 35 s)
make check                       # ruff, mypy, tests + 90 % coverage gate (currently 98 %), mock-model selftest
```

Now run the full benchmark pipeline against two **mock** models. They do not call an LLM; they exist to prove
the plumbing can both succeed and fail:

```bash
python -m bench.harness --llm mock:oracle --out results/selftest   # applies the reference fix
python -m bench.harness --llm mock:noop   --out results/selftest0  # does nothing and claims it is done
```

| backend | expected summary row | what it proves |
|---|---|---|
| `mock:oracle` | resolved **100%**, regression 0%, false-accept 0% | a correct fix is recognised as resolved |
| `mock:noop` | resolved **0%**, false-accept **100%** | a lie ("done") is caught by the hidden tests |

If `noop` ever shows a non-zero resolved rate, the harness is broken and no model result can be trusted.

## 3. Run it on a real model

```bash
ollama serve &                       # separate terminal
ollama pull llama3.1:8b              # or any chat model
vericode --repo bench/bugs/bug01_pagination/repo \
         --issue-file bench/bugs/bug01_pagination/issue.md \
         --verify --llm ollama:llama3.1:8b
# outputs: patch.diff, trajectory.json
```

The repo is copied to a temporary directory (and deleted afterwards); your files are never modified. If the
model server is not running you get exit code 2 and a clear message instead of a stack trace.

Full comparison (baseline vs verified, 3 seeds, all bugs):

```bash
python -m bench.harness --llm ollama:llama3.1:8b --seeds 3 --out results/run1
```

> Honest status: the review that produced this file ran every test and the mock pipeline, but **did not run a
> real LLM**. Treat real-model behaviour (format errors, step budgets) as untested until you try it.

## 4. Reading the code (suggested order)

| # | file | read it for |
|---|---|---|
| 1 | `vericode/prompts.py` | the exact JSON-action protocol the model must follow and the falsifier prompt |
| 2 | `vericode/tools.py` | the sandbox: path confinement, read-only tests, `run_pytest`, patch/diff, rollback |
| 3 | `vericode/agent.py` | `_loop` (tool loop), `_challenge` (one verification round), `run` (the orchestration) |
| 4 | `vericode/falsify.py` | turning the model's reply into a pytest file |
| 5 | `vericode/llm.py` | `OllamaLLM`, `ScriptedLLM` (tests), `MockLLM` (pipeline checks) |
| 6 | `bench/harness.py` | `run_case` (one run), hidden-test evaluation, the summary table |
| 7 | `tests/` | how each rule above is pinned down |

### One run, step by step

1. `Workspace(repo)` copies the buggy repo to a temp dir and snapshots every file. Every test file that exists
   at this point becomes **protected**.
2. `Agent._loop` asks the model for one JSON action per turn (`read_file`, `edit_file`, `run_tests`, ...). Bad
   JSON costs a step but never crashes the run. `finish` ends the loop.
3. **Baseline arm:** stop here. **Verified arm:** `_challenge` first requires the visible suite to pass, then
   asks the model for adversarial tests derived from the *issue*, writes them to `tests/test_adv_rN.py`, and
   runs only that file.
4. A broken adversarial file (syntax error, collection error, zero tests, timeout) is **discarded**, not counted
   as a counterexample. A failing one is sent back to the agent as feedback, up to `--rounds` times.
5. The harness copies the final workspace next to the hidden tests and runs them. `resolved` means the hidden
   suite passes. The agent never sees these files.

## 5. The integrity rules, and how each is enforced

| rule | enforced by | pinned by test |
|---|---|---|
| paths cannot escape the repo | `Workspace._resolve` | `test_tools.py` |
| original tests are read-only | `protected` set + `_check_writable` | `test_tools.py` |
| **no `conftest.py` / `pytest.ini` / `tox.ini` / `setup.cfg` / `pyproject.toml` / `sitecustomize.py`** | `PYTEST_CONTROL_FILES` | `test_agent_cannot_create_pytest_control_files`, `test_conftest_cheat_no_longer_resolves_bug` |
| **test output cannot forge the counts** | results parsed from pytest's junit-xml | `test_test_output_cannot_forge_result_counts` |
| hidden tests never live in the workspace | `run_case` copies them in only for evaluation | `test_harness.py` |
| both arms get the same model, seed, budget | `AgentConfig` | `test_harness.py` |

The two **bold** rules were added during review. Before the change, an agent could write a `conftest.py` that
rewrote every failure to "passed" and be scored as having solved the bug with a zero-line patch.

## 6. Anatomy of a bug case

```
bench/bugs/bug01_pagination/
├── issue.md            what the agent sees (the only spec)
├── repo/               the buggy code + a few visible tests (these must FAIL on the buggy code)
├── hidden/             the real acceptance tests; never shown to the model
└── fix/                reference solution; used ONLY by mock:oracle
```

`tests/test_harness.py` checks automatically that each case fails visibly on the buggy code, is solved by
`fix/`, and is *not* solved by doing nothing.

### Add your own case

1. Copy a case directory and rename it `bugNN_topic`.
2. Write `repo/` with the bug and 1-2 visible tests that fail because of it.
3. Write `issue.md` stating **every** requirement the hidden tests check (the falsifier sees only this text).
4. Write `hidden/test_hidden.py` covering all of those requirements, including edge cases.
5. Put the correct code in `fix/` (same relative paths as in `repo/`).
6. `python -m pytest` — the parametrised harness tests pick the new case up automatically.

## 7. Reading the results

`results.jsonl` has one row per run; `summary.md` aggregates per mode:

* **resolved**: hidden suite passes (the ground truth).
* **regression**: a test that passed before the agent started no longer passes.
* **false-accept**: of the runs where the agent said "done", the share where hidden tests still fail. The
  headline metric: it is what self-verification is supposed to reduce.
* **counterexamples**: adversarial tests that failed. An upper bound on real defects found, because a wrong
  test also produces one.
* tool calls, tokens, patch lines, seconds: the cost of verification.

`trajectories/*.json` holds every step of every run; read the failing ones.

## 8. Limitations to state in any write-up

* Five tiny single-file bugs: far too few for conclusions. Add many more and run several seeds.
* The last revision after the final round is not re-challenged.
* A counterexample can come from a wrong test.
* The temp-directory workspace is **not a security sandbox**; run untrusted models in a container.
* Mock backends validate the pipeline only.

## 9. Troubleshooting

| symptom | cause / fix |
|---|---|
| `Could not reach the model server` (exit 2) | start `ollama serve`, `ollama pull <model>` |
| `bench.harness: error: bug directory ... not found` | run from a checkout, or pass `--bugs-dir PATH` |
| `ModuleNotFoundError: bench` when running a script directly | run from the project root, or `pip install -e .` |
| tests slow | each test spawns pytest subprocesses; about 20 s is normal |
