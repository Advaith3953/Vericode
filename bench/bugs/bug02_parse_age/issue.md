`parse_age` accepts values it should reject.

It accepts an `int` or a `str` (surrounding whitespace allowed) and returns an `int` in the range 0..150 inclusive. It must raise `ValueError` (never any other exception type) for: negative values, values above 150, empty or blank strings, non-numeric strings, decimals such as `"3.5"`, booleans, and `None`.
