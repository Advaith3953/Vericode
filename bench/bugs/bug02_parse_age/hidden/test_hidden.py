import pytest
from validators import parse_age


@pytest.mark.parametrize("v,exp", [("42", 42), (" 7 ", 7), (0, 0), ("150", 150), (150, 150), ("0", 0)])
def test_valid(v, exp):
    assert parse_age(v) == exp


@pytest.mark.parametrize("v", ["151", 151, "-1", -5, "", "  ", "abc", "3.5", 3.5, True, False, None])
def test_invalid_raises_value_error(v):
    with pytest.raises(ValueError):
        parse_age(v)
