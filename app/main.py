"""
app/main.py
-----------
FastAPI application.

The single endpoint POST /webhook:
  1. Verifies the GitHub HMAC-SHA256 signature.
  2. Drops a job into Redis via Celery.
  3. Returns 200 OK immediately so GitHub doesn't time out.
"""

import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.tasks import review_pull_request

load_dotenv()

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"].encode()

app = FastAPI(title="PR Review Bot")


def _verify_signature(body: bytes, signature_header: str | None) -> None:
    """
    GitHub signs every webhook payload with HMAC-SHA256.
    The header looks like: X-Hub-Signature-256: sha256=<hex_digest>
    We verify it here to reject any forged or tampered requests.
    """
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="HMAC signature mismatch")


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    """
    Receive a GitHub webhook, verify it, and enqueue a review job.
    Responds immediately with 200 so GitHub doesn't mark delivery as failed.
    """
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    # We only care about pull_request events
    if x_github_event != "pull_request":
        return JSONResponse({"status": "ignored", "reason": f"event={x_github_event}"})

    payload = await request.json()
    action = payload.get("action")

    # Only review when a PR is opened, reopened, or new commits are pushed
    if action not in {"opened", "reopened", "synchronize"}:
        return JSONResponse({"status": "ignored", "reason": f"action={action}"})

    pr_number = payload["pull_request"]["number"]
    repo_full_name = payload["repository"]["full_name"]   # e.g. "owner/repo"
    head_sha = payload["pull_request"]["head"]["sha"]

    # Enqueue the job — Celery will process it asynchronously
    review_pull_request.delay(repo_full_name, pr_number, head_sha)

    return JSONResponse({"status": "queued", "pr": pr_number})


@app.get("/health")
def health():
    """Simple liveness probe."""
    return {"status": "ok"}
