"""Shared OpenAI client helpers: JSON-mode calls with fence stripping and validation."""

import json
import re

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings

_PLACEHOLDER_KEYS = {"", "your-openai-api-key-here", "sk-your-key-here"}


def has_valid_api_key() -> bool:
    key = settings.openai_api_key.strip()
    return bool(key) and key not in _PLACEHOLDER_KEYS and not key.startswith("your-")


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def call_json_llm(system_prompt: str, user_prompt: str, schema: type[BaseModel], *, max_chars: int = 100_000):
    """Call the LLM in JSON mode and validate the response against a pydantic schema.

    Raises on any failure — callers are expected to fall back to heuristics.
    """
    if not has_valid_api_key():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    truncated = user_prompt[:max_chars]
    if len(user_prompt) > max_chars:
        truncated += "\n\n[Document truncated for processing]"

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": truncated},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("LLM returned an empty response")

    cleaned = _strip_json_fences(raw_content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned malformed JSON: {exc}") from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"LLM JSON does not match schema {schema.__name__}: {exc}") from exc


def call_chat_llm(system_prompt: str, messages: list[dict]) -> str:
    """Plain conversational completion (no JSON mode) — used for chat and email drafting."""
    if not has_valid_api_key():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "system", "content": system_prompt}, *messages],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""
