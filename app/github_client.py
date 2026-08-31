"""
All communication with the GitHub REST API.

GitHub API docs: https://docs.github.com/en/rest

We use httpx (a modern Python HTTP client) with a shared session so
connections are reused across calls within the same task.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
BASE_URL = "https://api.github.com"

# A single client reused across calls (connection pooling)
_client = httpx.Client(
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    timeout=30.0,
)


def fetch_pr_diff(repo_full_name: str, pr_number: int) -> str:
    """
    Download the unified diff for a pull request.

    GitHub returns the diff when we set Accept: application/vnd.github.diff
    """
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}"
    response = _client.get(
        url,
        headers={"Accept": "application/vnd.github.diff"},
    )
    response.raise_for_status()
    return response.text


def get_file_content(repo_full_name: str, file_path: str, ref: str) -> str:
    """
    Fetch the raw content of a file at a specific commit SHA.

    Used by context.py to read the full file so Tree-sitter can parse it.
    """
    url = f"{BASE_URL}/repos/{repo_full_name}/contents/{file_path}"
    response = _client.get(url, params={"ref": ref})
    response.raise_for_status()

    # GitHub returns base64-encoded content
    import base64
    data = response.json()
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def get_file_lines(
    repo_full_name: str, ref: str, filename: str, start: int, end: int
) -> list[str]:
    """
    Return specific lines from a file at a given commit.

    Parameters
    ----------
    start : int  (1-indexed, inclusive)
    end   : int  (1-indexed, inclusive)
    """
    content = get_file_content(repo_full_name, filename, ref)
    all_lines = content.splitlines()
    # Clamp to actual file bounds
    start = max(1, start)
    end = min(len(all_lines), end)
    return all_lines[start - 1 : end]


def search_code(repo_full_name: str, query: str) -> list[dict]:
    """
    Search the repo for code matching a query string.
    Used by find_callers() to locate call sites.

    Returns a list of {"filename": str, "line": int} dicts.
    """
    url = f"{BASE_URL}/search/code"
    response = _client.get(
        url,
        params={"q": f"{query} repo:{repo_full_name}", "per_page": 20},
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    return [{"filename": item["path"]} for item in items]


def post_review_comments(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    comments: list[dict],
) -> None:
    """
    Post a pull request review with inline comments.

    Each comment in `comments` must have:
        path : str   — file path relative to repo root
        line : int   — line number in the diff (right side)
        body : str   — the review comment text

    GitHub API: POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews
    """
    url = f"{BASE_URL}/repos/{repo_full_name}/pulls/{pr_number}/reviews"

    payload = {
        "commit_id": commit_sha,
        "event": "COMMENT",   # COMMENT = leave comments without approving/requesting changes
        "comments": [
            {
                "path": c["path"],
                "line": c["line"],
                "body": c["body"],
                "side": "RIGHT",   # RIGHT = the new version of the file
            }
            for c in comments
        ],
    }

    response = _client.post(url, json=payload)
    response.raise_for_status()
