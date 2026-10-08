import time


def is_expired(issued_at, ttl, now=None):
    """Return True if a token issued at `issued_at` is no longer valid."""
    now = time.time() if now is None else now
    return now - issued_at > ttl
