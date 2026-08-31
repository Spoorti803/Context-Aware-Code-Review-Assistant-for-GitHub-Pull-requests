"""
tests/test_context.py
---------------------
Unit tests for ranking and (where possible without a running language server)
the Tree-sitter extraction logic.

Run with:  pytest tests/test_context.py -v
"""

from app.context import rank_and_select


def _make_snippet(changed_count: int, fn_lines: int, callers: int) -> dict:
    return {
        "filename": "app/foo.py",
        "start_line": 1,
        "changed_lines": [{"op": "+"} for _ in range(changed_count)],
        "function_body": {
            "name": "foo",
            "start_line": 1,
            "end_line": fn_lines,
            "source": "\n".join(["x = 1"] * fn_lines),
        },
        "callers": [{"filename": "bar.py", "line": i, "snippet": "foo()"} for i in range(callers)],
    }


def test_rank_and_select_returns_at_most_max():
    snippets = [_make_snippet(1, 5, 0) for _ in range(20)]
    result = rank_and_select(snippets, max_snippets=7)
    assert len(result) <= 7


def test_rank_and_select_prefers_more_changes():
    low = _make_snippet(changed_count=1, fn_lines=5, callers=0)
    high = _make_snippet(changed_count=10, fn_lines=5, callers=0)
    result = rank_and_select([low, high], max_snippets=2)
    # The snippet with 10 changed lines should rank first
    assert result[0]["changed_lines"] == high["changed_lines"]


def test_rank_and_select_prefers_more_callers():
    few = _make_snippet(changed_count=1, fn_lines=5, callers=1)
    many = _make_snippet(changed_count=1, fn_lines=5, callers=5)
    result = rank_and_select([few, many], max_snippets=2)
    assert len(result[0]["callers"]) == 5


def test_rank_and_select_empty_list():
    assert rank_and_select([]) == []


def test_rank_and_select_single_item():
    snippet = _make_snippet(2, 10, 3)
    result = rank_and_select([snippet], max_snippets=5)
    assert result == [snippet]
