import functools


def memoize(fn):
    cache = {}

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        key = args
        if key not in cache:
            cache[key] = fn(*args, **kwargs)
        return cache[key]

    wrapper.cache = cache
    wrapper.cache_clear = cache.clear
    return wrapper
