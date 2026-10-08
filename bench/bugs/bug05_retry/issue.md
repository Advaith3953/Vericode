`retry()` silently returns `None` when every attempt fails.

When all attempts are exhausted it must re-raise the last exception. It must not sleep after the final failed attempt. Exceptions not listed in `exceptions` must propagate immediately with no retry. `attempts < 1` must raise `ValueError`. On success it returns the function's return value.
