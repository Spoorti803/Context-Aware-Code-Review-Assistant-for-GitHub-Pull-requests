"""
tests/test_diff_parser.py
-------------------------
Unit tests for app/diff_parser.py.

Run with:  pytest tests/test_diff_parser.py -v
"""

from app.diff_parser import parse_diff

SAMPLE_DIFF = """\
diff --git a/app/main.py b/app/main.py
--- a/app/main.py
+++ b/app/main.py
@@ -10,6 +10,8 @@ def hello():
-    print("hi")
+    print("hello")
+    return True
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 # My project
+Added a new section.
"""


def test_parse_diff_finds_both_files():
    files = parse_diff(SAMPLE_DIFF)
    filenames = [f["filename"] for f in files]
    assert "app/main.py" in filenames
    assert "README.md" in filenames


def test_parse_diff_py_hunk():
    files = parse_diff(SAMPLE_DIFF)
    py_file = next(f for f in files if f["filename"] == "app/main.py")
    assert len(py_file["hunks"]) == 1
    hunk = py_file["hunks"][0]
    assert hunk["start"] == 10

    ops = [l["op"] for l in hunk["lines"]]
    assert "-" in ops
    assert "+" in ops


def test_parse_diff_added_line_content():
    files = parse_diff(SAMPLE_DIFF)
    py_file = next(f for f in files if f["filename"] == "app/main.py")
    hunk = py_file["hunks"][0]
    added = [l["content"] for l in hunk["lines"] if l["op"] == "+"]
    assert '    print("hello")' in added
    assert "    return True" in added


def test_parse_diff_empty_diff():
    assert parse_diff("") == []


def test_parse_diff_no_hunks_ignored():
    diff = "diff --git a/foo b/foo\n--- a/foo\n+++ b/foo\n"
    result = parse_diff(diff)
    # File has no hunks — should be excluded
    assert result == []
