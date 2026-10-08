from pagination import paginate, total_pages


def test_first_page_returns_first_items():
    assert paginate([1, 2, 3, 4, 5, 6], 1, 2) == [1, 2]


def test_total_pages_exact_multiple():
    assert total_pages(10, 5) == 2
