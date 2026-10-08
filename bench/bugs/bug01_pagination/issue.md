`paginate()` returns the wrong items.

`paginate(items, page, per_page)` uses 1-indexed pages: page 1 must return the first `per_page` items. Pages past the end return `[]`. `page < 1` or `per_page < 1` must raise `ValueError`.

`total_pages(n_items, per_page)` must round up (11 items, 5 per page -> 3; 0 items -> 0) and raise `ValueError` for `per_page < 1`.
