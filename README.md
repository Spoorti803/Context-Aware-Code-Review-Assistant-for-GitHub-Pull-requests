
# PR Review Bot

An automated code review bot that listens to GitHub pull request events, retrieves rich code context using Tree-sitter, and posts inline review comments via an LLM (Claude or GPT-4o).

---

## Table of Contents
1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Project structure](#project-structure)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the bot](#running-the-bot)
7. [Setting up the GitHub webhook](#setting-up-the-github-webhook)
8. [Exposing localhost with ngrok (for development)](#exposing-localhost-with-ngrok-for-development)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)

---

## How it works

1. A developer opens a Pull Request on GitHub.
2. GitHub fires a webhook `POST /webhook` to your server.
3. FastAPI receives it, verifies the HMAC-SHA256 signature, and drops a job into **Redis**.
4. FastAPI instantly responds `200 OK` to GitHub (so GitHub doesn't time out).
5. A **Celery** worker picks up the job and runs the context retrieval pipeline:
   - Fetches the PR diff via the GitHub API.
   - Parses changed files and line numbers.
   - Gathers ±20 surrounding lines for context.
   - Extracts full function bodies and their callers using **Tree-sitter**.
   - Ranks and selects the top 5–8 most relevant snippets.
6. Builds a prompt and sends it to the LLM (Claude or GPT-4o).
7. Parses the JSON response and posts inline review comments back to GitHub.

---

## Prerequisites

Install these before anything else:

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| Redis | 7+ | https://redis.io/docs/install |
| Git | any | https://git-scm.com |
| ngrok (dev only) | any | https://ngrok.com |

You also need accounts/tokens for:
- **GitHub** — a Personal Access Token (PAT) with `repo` scope.
- **Anthropic** or **OpenAI** — an API key for the LLM.

---

## Project structure

```
pr_review_bot/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + webhook endpoint
│   ├── worker.py          # Celery app definition
│   ├── tasks.py           # Celery task: full review pipeline
│   ├── github_client.py   # GitHub API helpers
│   ├── diff_parser.py     # Parse unified diffs
│   ├── context.py         # Tree-sitter context retrieval
│   ├── prompt_builder.py  # Build LLM prompt
│   └── llm_client.py      # Call Claude / GPT-4o
├── tests/
│   ├── test_diff_parser.py
│   ├── test_context.py
│   └── test_webhook.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone and enter the project

```bash
git clone https://github.com/YOUR_USERNAME/pr_review_bot.git
cd pr_review_bot
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Tree-sitter language grammars

Tree-sitter needs compiled language binaries. Run this once:

```bash
python -c "
from tree_sitter import Language
import subprocess, os

# Download grammars
for repo in [
    'https://github.com/tree-sitter/tree-sitter-python',
    'https://github.com/tree-sitter/tree-sitter-javascript',
]:
    name = repo.split('/')[-1]
    if not os.path.exists(name):
        subprocess.run(['git', 'clone', '--depth=1', repo])

Language.build_library(
    'build/languages.so',
    ['tree-sitter-python', 'tree-sitter-javascript'],
)
print('Tree-sitter grammars built.')
"
```

### 5. Start Redis

```bash
# macOS (Homebrew)
brew services start redis

# Ubuntu / Debian
sudo systemctl start redis-server

# Or run in Docker
docker run -d -p 6379:6379 redis:7
```

Verify Redis is running:
```bash
redis-cli ping   # should print: PONG
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# GitHub
GITHUB_TOKEN=ghp_your_personal_access_token_here
GITHUB_WEBHOOK_SECRET=a_random_string_you_choose

# LLM — pick one
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # optional, only if using GPT-4o
LLM_PROVIDER=anthropic         # "anthropic" or "openai"

# Redis
REDIS_URL=redis://localhost:6379/0
```

**How to get a GitHub PAT:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic).
2. Click "Generate new token".
3. Select scopes: `repo` (full control of private repos).
4. Copy the token — it's only shown once.

**Choosing a webhook secret:**
- Just pick any random string, e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`.
- You'll paste this same string into the GitHub webhook settings later.

---

## Running the bot

You need **three terminal windows** (or use a process manager like `honcho`).

### Terminal 1 — FastAPI server

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see: `Uvicorn running on http://0.0.0.0:8000`

### Terminal 2 — Celery worker

```bash
source venv/bin/activate
celery -A app.worker worker --loglevel=info
```

You should see: `celery@hostname ready.`

### Terminal 3 — Redis (if not running as a service)

```bash
redis-server
```

---

## Setting up the GitHub webhook

### Step 1 — Expose your local server (development)

See the [ngrok section](#exposing-localhost-with-ngrok-for-development) below to get a public URL.

### Step 2 — Add the webhook to your GitHub repo

1. Go to your repo on GitHub → **Settings** → **Webhooks** → **Add webhook**.
2. Fill in:
   - **Payload URL**: `https://YOUR_NGROK_URL/webhook`
   - **Content type**: `application/json`
   - **Secret**: the same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
   - **Which events?** → Select "Pull requests"
3. Click **Add webhook**.
4. GitHub will send a test ping. You should see a green checkmark.

---

## Exposing localhost with ngrok (for development)

ngrok creates a public HTTPS tunnel to your local machine.

```bash
# Install (if not done)
brew install ngrok       # macOS
# or download from https://ngrok.com/download

# Authenticate (once, free account)
ngrok config add-authtoken YOUR_NGROK_TOKEN

# Start tunnel
ngrok http 8000
```

ngrok will show something like:
```
Forwarding   https://abc123.ngrok.io -> http://localhost:8000
```

Use `https://abc123.ngrok.io` as your webhook base URL.

> **Note:** The free ngrok URL changes every time you restart ngrok. Update your GitHub webhook URL whenever this happens.

---

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

### Manual end-to-end test

1. Make sure all three services are running (FastAPI, Celery, Redis).
2. Open a real pull request in your repo (or re-open a draft PR).
3. Wait ~10–30 seconds.
4. Refresh the PR page — you should see inline review comments posted by the bot.

### Test the webhook endpoint manually

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=PLACEHOLDER" \
  -d '{"action":"opened","pull_request":{"number":1,"head":{"sha":"abc"}},"repository":{"full_name":"owner/repo"}}'
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `redis.exceptions.ConnectionError` | Redis isn't running. Start it with `redis-server`. |
| `HMAC signature mismatch` | Your `GITHUB_WEBHOOK_SECRET` in `.env` doesn't match what you set in GitHub. |
| Celery task never runs | Check Terminal 2 — the Celery worker must be running and connected to Redis. |
| No comments posted | Check `GITHUB_TOKEN` has `repo` scope. Check the LLM API key is correct. Look at Celery logs for errors. |
| Tree-sitter `languages.so` not found | Re-run the build step in the Installation section. |
| ngrok URL expired | Restart ngrok and update the GitHub webhook Payload URL. |
