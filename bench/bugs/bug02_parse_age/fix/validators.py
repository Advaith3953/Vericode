def parse_age(value):
    """Parse a user-supplied age."""
    if value is None or isinstance(value, bool):
        raise ValueError("invalid age")
    try:
        age = int(str(value).strip())
    except ValueError:
        raise ValueError("invalid age") from None
    if not 0 <= age <= 150:
        raise ValueError("age out of range")
    return age
