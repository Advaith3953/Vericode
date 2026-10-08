import time


def retry(fn, attempts=3, delay=0.0, exceptions=(Exception,), sleep=time.sleep):
    """Call fn() until it succeeds or attempts run out."""
    for _ in range(attempts):
        try:
            return fn()
        except exceptions:
            sleep(delay)
    return None
