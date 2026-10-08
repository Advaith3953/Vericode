import pytest
from cache import memoize


def test_kwarg_order_shares_entry():
    calls = []

    @memoize
    def f(a=0, b=0):
        calls.append(1)
        return a + b

    f(a=1, b=2)
    f(b=2, a=1)
    assert len(calls) == 1


def test_unhashable_positional_not_cached_no_error():
    calls = []

    @memoize
    def f(x):
        calls.append(1)
        return len(x)

    assert f([1, 2]) == 2
    assert f([1, 2]) == 2
    assert len(calls) == 2


def test_unhashable_kwarg_not_cached_no_error():
    calls = []

    @memoize
    def f(x=None):
        calls.append(1)
        return len(x)

    assert f(x=[1]) == 1
    assert f(x=[1]) == 1
    assert len(calls) == 2


def test_exceptions_not_cached():
    state = {"n": 0}

    @memoize
    def f(x):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("first call fails")
        return x

    with pytest.raises(RuntimeError):
        f(1)
    assert f(1) == 1


def test_cache_clear():
    calls = []

    @memoize
    def f(x):
        calls.append(1)
        return x

    f(1)
    f.cache_clear()
    f(1)
    assert len(calls) == 2
