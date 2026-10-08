import pytest
from validators import parse_age


def test_valid_string():
    assert parse_age("42") == 42


def test_negative_rejected():
    with pytest.raises(ValueError):
        parse_age("-5")
