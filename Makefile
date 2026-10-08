.PHONY: install lint typecheck test cov check clean
PY ?= python3

install:           ## editable install with dev tools
	$(PY) -m pip install -e '.[dev]'

lint:              ## style + bug-pattern lint
	ruff check .

typecheck:
	mypy vericode bench/harness.py

test:              ## unit + integration tests
	$(PY) -m pytest -q

cov:               ## tests with coverage gate (fails below 90%)
	$(PY) -m pytest -q --cov --cov-fail-under=90

selftest:          ## benchmark pipeline with mock models: oracle must solve 5/5, noop must solve 0/5
	$(PY) -m bench.harness --llm mock:oracle --out results/selftest-oracle
	$(PY) -m bench.harness --llm mock:noop --out results/selftest-noop
	$(PY) scripts/check_selftest.py results/selftest-oracle results/selftest-noop

check: lint typecheck cov selftest   ## everything CI runs

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage results
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
