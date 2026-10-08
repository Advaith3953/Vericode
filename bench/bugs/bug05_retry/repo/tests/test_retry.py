import pytest
from retry import retry


def make_flaky(n_fail, exc=ValueError):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] <= n_fail:
            raise exc("boom")
        return "ok"

    fn.state = state
    return fn


def test_succeeds_after_failures():
    assert retry(make_flaky(2), attempts=3, sleep=lambda s: None) == "ok"


def test_raises_when_exhausted():
    with pytest.raises(ValueError):
        retry(make_flaky(5), attempts=3, sleep=lambda s: None)
