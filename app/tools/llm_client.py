"""Thin async wrapper around whichever LLM provider is configured.

Every agent reasons through this one entry point: `complete()` for free text
and `complete_json()` for schema-constrained structured output. Swapping
providers is an env var change, not a code change.
"""
from __future__ import annotations

import json
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.provider = settings.llm_provider.lower()

        if self.provider == "anthropic":
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self._model = settings.anthropic_model
        elif self.provider == "openai":
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model
        elif self.provider == "mistral":
            from mistralai.client import Mistral

            self._client = Mistral(api_key=settings.mistral_api_key)
            self._model = settings.mistral_model
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Return raw text completion."""
        if self.provider == "anthropic":
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        if self.provider == "mistral":
            resp = await self._client.chat.complete_async(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content or ""
        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    async def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict[str, Any]:
        """Return a completion parsed as JSON. Instructs the model explicitly and repairs on failure."""
        json_system = system + "\n\nRespond with ONLY valid JSON. No markdown fences, no commentary."
        text = await self.complete(json_system, user, max_tokens=max_tokens)
        return _parse_json_loose(text)


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON output: %s | raw=%s", exc, text[:500])
        raise


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
