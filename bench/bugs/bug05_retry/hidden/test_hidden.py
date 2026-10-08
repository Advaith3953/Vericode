import pytest
from retry import retry


def failing(exc=ValueError):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        raise exc("boom")

    fn.state = state
    return fn


def test_no_sleep_after_last_attempt():
    sleeps = []
    with pytest.raises(ValueError):
        retry(failing(), attempts=3, delay=1.5, sleep=sleeps.append)
    assert sleeps == [1.5, 1.5]


def test_unlisted_exception_propagates_immediately():
    fn = failing(KeyError)
    with pytest.raises(KeyError):
        retry(fn, attempts=5, exceptions=(ValueError,), sleep=lambda s: None)
    assert fn.state["calls"] == 1


def test_attempts_must_be_positive():
    with pytest.raises(ValueError):
        retry(lambda: 1, attempts=0)


def test_returns_value_on_first_success():
    assert retry(lambda: 42, attempts=1) == 42


def test_last_exception_is_reraised():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RuntimeError(f"fail {calls['n']}")

    with pytest.raises(RuntimeError, match="fail 3"):
        retry(fn, attempts=3, sleep=lambda s: None)
