"""
app/llm_client.py
-----------------
Send the prompt to the configured LLM provider and return the raw response text.

Supported providers (set LLM_PROVIDER in .env):
  - "groq"       → Groq (free, fast) — recommended
  - "gemini"     → Google Gemini (free)
  - "anthropic"  → Claude (paid, small free credits)
  - "openai"     → GPT-4o (paid)
"""

import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

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


def analyze_with_llm(messages: list[dict]) -> str:
    """
    Send `messages` to the configured LLM and return the raw text response.
    """
    if LLM_PROVIDER == "groq":
        return _call_groq(messages)
    elif LLM_PROVIDER == "gemini":
        return _call_gemini(messages)
    elif LLM_PROVIDER == "anthropic":
        return _call_anthropic(messages)
    elif LLM_PROVIDER == "openai":
        return _call_openai(messages)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. "
            "Choose from: groq, gemini, anthropic, openai"
        )


def _call_groq(messages: list[dict]) -> str:
    """
    Call Groq's API (free tier available).
    Model: llama-3.3-70b-versatile — very capable, free on Groq.
    Get your key at: https://console.groq.com
    """
    import httpx

    api_key = os.environ["GROQ_API_KEY"]
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": full_messages,
            "max_tokens": 2048,
            "temperature": 0,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_gemini(messages: list[dict]) -> str:
    """
    Call Google Gemini API (free tier available).
    Model: gemini-1.5-flash — fast and free.
    Get your key at: https://aistudio.google.com
    """
    import httpx

    api_key = os.environ["GEMINI_API_KEY"]
    user_text = SYSTEM_PROMPT + "\n\n" + messages[-1]["content"]

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
        json={
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0},
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_anthropic(messages: list[dict]) -> str:
    """Call Claude via the Anthropic SDK."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


def _call_openai(messages: list[dict]) -> str:
    """Call GPT-4o via the OpenAI SDK."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=full_messages,
        max_tokens=2048,
        temperature=0,
    )
    return response.choices[0].message.content
