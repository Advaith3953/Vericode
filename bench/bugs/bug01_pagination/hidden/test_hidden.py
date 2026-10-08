import pytest
from pagination import paginate, total_pages


def test_pages_partition_the_list():
    items, out = list(range(11)), []
    for p in range(1, 4):
        out += paginate(items, p, 5)
    assert out == items


def test_beyond_last_page_is_empty():
    assert paginate([1, 2, 3], 5, 2) == []


def test_total_pages_rounds_up():
    assert total_pages(11, 5) == 3


def test_total_pages_zero_items():
    assert total_pages(0, 5) == 0


@pytest.mark.parametrize("page,per", [(0, 2), (-1, 2), (1, 0), (1, -3)])
def test_invalid_arguments(page, per):
    with pytest.raises(ValueError):
        paginate([1, 2, 3], page, per)


def test_total_pages_invalid_per_page():
    with pytest.raises(ValueError):
        total_pages(5, 0)
