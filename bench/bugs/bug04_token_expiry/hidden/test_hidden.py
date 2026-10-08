import time
from auth import is_expired


def test_just_before_expiry_is_valid():
    assert is_expired(0, 10, now=9.99) is False


def test_zero_ttl_always_expired():
    assert is_expired(5, 0, now=5) is True


def test_negative_ttl_always_expired():
    assert is_expired(5, -1, now=5) is True


def test_future_token_is_expired():
    assert is_expired(100, 10, now=50) is True


def test_issued_now_is_valid():
    assert is_expired(50, 10, now=50) is False


def test_default_now_uses_clock():
    assert is_expired(time.time(), 60) is False
    assert is_expired(time.time() - 120, 60) is True
