from auth import is_expired


def test_old_token_is_expired():
    assert is_expired(0, 10, now=100) is True


def test_expired_exactly_at_ttl():
    assert is_expired(0, 10, now=10) is True
