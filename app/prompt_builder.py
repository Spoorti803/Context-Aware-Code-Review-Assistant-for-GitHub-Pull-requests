"""
app/prompt_builder.py
---------------------
Assembles the retrieved context snippets into an LLM prompt.

The prompt instructs the LLM to act as a code reviewer and return
structured JSON so we can parse it and post inline GitHub comments.
"""

import json


SYSTEM_PROMPT = """You are an expert code reviewer. You will be given a pull request diff along with relevant context (the full function body and its call sites).

Your job is to identify real issues such as:
- Bugs or logic errors
- Missing error handling
- Security vulnerabilities (SQL injection, XSS, unvalidated input, etc.)
- Performance problems
- Breaking changes to the public API or callers

Do NOT comment on style, formatting, naming conventions, or missing tests unless they hide a functional bug.

Respond ONLY with a valid JSON array. Each element must be an object with exactly these keys:
  "path"  : string  — the file path relative to the repo root
  "line"  : integer — the line number in the new version of the file
  "body"  : string  — a concise, actionable review comment (max 3 sentences)

If you find no issues, respond with an empty array: []

Do not include any text outside the JSON array."""


def build_prompt(snippets: list[dict]) -> list[dict]:
    """
    Build the messages list to send to the LLM.

    Returns
    -------
    List of {"role": str, "content": str} message dicts.
    """
    parts = []

    for i, snippet in enumerate(snippets, 1):
        filename = snippet["filename"]
        start_line = snippet["start_line"]
        changed_lines = snippet.get("changed_lines", [])
        function_info = snippet.get("function_body")
        callers = snippet.get("callers", [])

        parts.append(f"### Change {i}: `{filename}` (starting at line {start_line})\n")

        # The actual diff lines for this hunk
        if changed_lines:
            parts.append("**Changed lines:**\n```diff")
            for l in changed_lines:
                parts.append(f"{l['op']} {l['content']}")
            parts.append("```\n")

        # The full function body
        if function_info:
            parts.append(
                f"**Enclosing function `{function_info['name']}` "
                f"(lines {function_info['start_line']}–{function_info['end_line']}):**\n"
                f"```\n{function_info['source']}\n```\n"
            )

        # Call sites
        if callers:
            parts.append("**Call sites (callers of this function):**")
            for caller in callers:
                parts.append(
                    f"- `{caller['filename']}` line {caller['line']}: `{caller['snippet'].strip()}`"
                )
            parts.append("")

    user_content = "\n".join(parts)

    return [
        {"role": "user", "content": user_content},
    ]
