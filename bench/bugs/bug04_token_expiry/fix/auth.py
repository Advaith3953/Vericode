import time


def is_expired(issued_at, ttl, now=None):
    """Return True if a token issued at `issued_at` is no longer valid."""
    now = time.time() if now is None else now
    if ttl <= 0 or issued_at > now:
        return True
    return now - issued_at >= ttl
