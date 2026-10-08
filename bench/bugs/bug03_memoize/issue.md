`memoize` returns stale results when a function is called with different keyword arguments (`f(1, b=2)` and `f(1, b=3)` return the same value).

Fix it. Keyword argument order must not matter (`f(a=1, b=2)` and `f(b=2, a=1)` share one cache entry). If any argument is unhashable (for example a list), call the function normally without caching and without raising `TypeError`. Exceptions must not be cached. `wrapper.cache_clear()` must empty the cache.
