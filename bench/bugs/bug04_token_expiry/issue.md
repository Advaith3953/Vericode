Authentication timeout bug: tokens are still accepted at the exact moment they should expire.

A token is valid for `ttl` seconds. `is_expired(issued_at, ttl, now=None)` must return `True` when `now - issued_at >= ttl`. Tokens with `ttl <= 0` are always expired. Tokens issued in the future (`issued_at > now`) are invalid and must also be reported as expired. `now` defaults to the current time.
