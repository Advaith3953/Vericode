import time


def retry(fn, attempts=3, delay=0.0, exceptions=(Exception,), sleep=time.sleep):
    """Call fn() until it succeeds or attempts run out."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for i in range(attempts):
        try:
            return fn()
        except exceptions:
            if i == attempts - 1:
                raise
            sleep(delay)
