"""
tests/test_webhook.py
Integration tests for the FastAPI webhook endpoint.

Run with:  pytest tests/test_webhook.py -v

We mock out the Celery task so tests don't need Redis or the full pipeline.
"""

import hashlib
import hmac
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Set a fake secret before importing the app
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test_secret")
os.environ.setdefault("GITHUB_TOKEN", "fake_token")

from app.main import app

client = TestClient(app)
SECRET = b"test_secret"


def _sign(payload: bytes) -> str:
    """Generate the X-Hub-Signature-256 header for a payload."""
    digest = hmac.new(SECRET, payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 42,
        "head": {"sha": "abc123"},
    },
    "repository": {"full_name": "owner/repo"},
}


def _post_webhook(payload: dict, event: str = "pull_request", secret: bytes = SECRET):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(body) if secret else "bad",
            "X-GitHub-Event": event,
        },
    )


@patch("app.main.review_pull_request")
def test_webhook_queues_task(mock_task):
    response = _post_webhook(PR_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    mock_task.delay.assert_called_once_with("owner/repo", 42, "abc123")


def test_webhook_rejects_bad_signature():
    body = json.dumps(PR_PAYLOAD).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=badhash",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 401


def test_webhook_rejects_missing_signature():
    body = json.dumps(PR_PAYLOAD).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert response.status_code == 401


@patch("app.main.review_pull_request")
def test_webhook_ignores_push_events(mock_task):
    response = _post_webhook(PR_PAYLOAD, event="push")
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    mock_task.delay.assert_not_called()


@patch("app.main.review_pull_request")
def test_webhook_ignores_closed_action(mock_task):
    payload = {**PR_PAYLOAD, "action": "closed"}
    response = _post_webhook(payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    mock_task.delay.assert_not_called()


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
