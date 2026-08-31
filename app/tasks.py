"""
app/tasks.py
------------
The main Celery task that orchestrates the full review pipeline:

  1. Fetch PR diff from GitHub
  2. Parse changed files + line numbers
  3. Get ±20 surrounding lines for each changed chunk
  4. Extract the enclosing function body (Tree-sitter)
  5. Find callers of that function (Tree-sitter)
  6. Rank and select the top 5–8 context snippets
  7. Build a prompt
  8. Call the LLM
  9. Parse the JSON response
  10. Post inline review comments to GitHub
"""

import logging

from app.worker import celery_app
from app.github_client import fetch_pr_diff, post_review_comments
from app.diff_parser import parse_diff
from app.context import get_surrounding_lines, extract_function, find_callers, rank_and_select
from app.prompt_builder import build_prompt
from app.llm_client import analyze_with_llm

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,   # seconds between retries
    name="tasks.review_pull_request",
)
def review_pull_request(self, repo_full_name: str, pr_number: int, head_sha: str):
    """
    Full review pipeline for a single pull request.

    Parameters
    ----------
    repo_full_name : str
        GitHub repo in "owner/repo" format, e.g. "acme/my-service"
    pr_number : int
        The pull request number
    head_sha : str
        The SHA of the head commit (used to post inline comments at the right commit)
    """
    logger.info(f"Starting review: {repo_full_name} PR#{pr_number} @ {head_sha}")

    try:
        # ── Step 1 & 2: Fetch and parse diff ────────────────────────────────
        raw_diff = fetch_pr_diff(repo_full_name, pr_number)
        changed_files = parse_diff(raw_diff)
        # changed_files is a list of:
        # {"filename": str, "hunks": [{"start": int, "lines": [...]}]}

        if not changed_files:
            logger.info("No changed files found — nothing to review.")
            return

        # ── Steps 3–6: Context retrieval ────────────────────────────────────
        context_snippets = []

        for file_info in changed_files:
            filename = file_info["filename"]

            # Skip non-code files
            if not _is_code_file(filename):
                continue

            for hunk in file_info["hunks"]:
                start_line = hunk["start"]
                changed_lines = hunk["lines"]

                # Get ±20 lines of surrounding context from GitHub
                surrounding = get_surrounding_lines(
                    repo_full_name, head_sha, filename, start_line, window=20
                )

                # Extract the full function body that contains the change
                function_body = extract_function(filename, surrounding, start_line)

                # Find other places in the repo that call this function
                callers = find_callers(repo_full_name, head_sha, function_body)

                context_snippets.append({
                    "filename": filename,
                    "start_line": start_line,
                    "changed_lines": changed_lines,
                    "surrounding": surrounding,
                    "function_body": function_body,
                    "callers": callers,
                })

        # Pick the most relevant 5–8 snippets to stay within LLM context limits
        top_snippets = rank_and_select(context_snippets, max_snippets=7)

        # ── Step 7: Build prompt ─────────────────────────────────────────────
        prompt = build_prompt(top_snippets)

        # ── Step 8: Call LLM ─────────────────────────────────────────────────
        raw_response = analyze_with_llm(prompt)

        # ── Step 9: Parse JSON response ──────────────────────────────────────
        # The LLM returns a list of comment objects:
        # [{"path": "file.py", "line": 42, "body": "Consider using..."}]
        import json
        comments = json.loads(raw_response)

        # ── Step 10: Post to GitHub ───────────────────────────────────────────
        if comments:
            post_review_comments(repo_full_name, pr_number, head_sha, comments)
            logger.info(f"Posted {len(comments)} review comment(s) on PR#{pr_number}")
        else:
            logger.info("LLM returned no comments — PR looks clean!")

    except Exception as exc:
        logger.error(f"Review failed for PR#{pr_number}: {exc}", exc_info=True)
        # Celery will retry up to max_retries times
        raise self.retry(exc=exc)


def _is_code_file(filename: str) -> bool:
    """Return True for file extensions we can parse with Tree-sitter."""
    CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb", ".java", ".c", ".cpp", ".h"}
    return any(filename.endswith(ext) for ext in CODE_EXTENSIONS)
