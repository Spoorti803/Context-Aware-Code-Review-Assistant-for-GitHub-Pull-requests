"""
Parse a unified diff (the format returned by GitHub) into a structured list
of changed files and their hunks.

A unified diff looks like:

    diff --git a/foo.py b/foo.py
    --- a/foo.py
    +++ b/foo.py
    @@ -10,6 +10,8 @@
     def hello():
    -    print("hi")
    +    print("hello")
    +    return True

We turn this into:
    [
        {
            "filename": "foo.py",
            "hunks": [
                {
                    "start": 10,       # first line of the hunk in the new file
                    "lines": [         # all changed lines (+ and -)
                        {"op": "-", "content": '    print("hi")'},
                        {"op": "+", "content": '    print("hello")'},
                        {"op": "+", "content": "    return True"},
                    ]
                }
            ]
        }
    ]
"""

import re


def parse_diff(raw_diff: str) -> list[dict]:
    """
    Parse a unified diff string.

    Returns
    -------
    list of file dicts, each containing "filename" and "hunks".
    """
    files = []
    current_file = None
    current_hunk = None

    for line in raw_diff.splitlines():

        # ── New file ────────────────────────────────────────────────────────
        if line.startswith("+++ b/"):
            filename = line[6:]   # strip "+++ b/"
            current_file = {"filename": filename, "hunks": []}
            files.append(current_file)
            current_hunk = None
            continue

        if line.startswith("--- ") or line.startswith("diff --git"):
            continue   # not useful to us

        # ── Hunk header: @@ -old_start,old_count +new_start,new_count @@ ───
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match and current_file is not None:
            new_start = int(hunk_match.group(1))
            current_hunk = {"start": new_start, "lines": []}
            current_file["hunks"].append(current_hunk)
            continue

        # ── Diff lines ───────────────────────────────────────────────────────
        if current_hunk is None:
            continue

        if line.startswith("+"):
            current_hunk["lines"].append({"op": "+", "content": line[1:]})
        elif line.startswith("-"):
            current_hunk["lines"].append({"op": "-", "content": line[1:]})
        # context lines (starting with space) are intentionally ignored here
        # because we fetch them separately via get_surrounding_lines()

    # Drop files with no hunks (e.g. pure metadata diffs)
    return [f for f in files if f["hunks"]]
