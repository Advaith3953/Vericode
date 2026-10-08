import functools


def memoize(fn):
    cache = {}

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        try:
            hash(key)
        except TypeError:
            return fn(*args, **kwargs)
        if key not in cache:
            cache[key] = fn(*args, **kwargs)
        return cache[key]

    wrapper.cache = cache
    wrapper.cache_clear = cache.clear
    return wrapper
