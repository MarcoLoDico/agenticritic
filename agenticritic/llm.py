"""OpenRouter client (OpenAI-compatible) with a JSON-returning helper."""

import asyncio
import json
import re

from openai import AsyncOpenAI

from . import config

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set (see .env.example)")
        _client = AsyncOpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
            default_headers={"X-Title": "agenticritic"},
        )
    return _client


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} or [...] block.
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


async def chat_json(
    messages: list[dict],
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    retries: int = 3,
):
    """Call the model and parse its reply as JSON, retrying on transport or parse errors."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client().chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                raise ValueError(f"reply truncated at max_tokens={max_tokens}")
            return _extract_json(choice.message.content or "")
        except Exception as e:  # noqa: BLE001 - network, rate limit, or bad JSON
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}")
