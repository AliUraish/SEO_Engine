"""LLM facade over the OpenAI Responses API. Agents call `structured()` with a Pydantic model and
get a validated instance back. When the key is missing or the network switch is off, `enabled`
is False and agents fall back to deterministic heuristics — nothing is ever sent."""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import assert_network, get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    enabled: bool

    async def structured(self, *, system: str, prompt: str, schema: type[T], effort: str = "medium", max_tokens: int = 16000) -> T: ...


class OpenAILLM:
    enabled = True

    def __init__(self, model: str, api_key: str | None, base_url: str | None = None, reasoning: bool = False) -> None:
        self.model = model
        self.reasoning = reasoning
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def structured(self, *, system: str, prompt: str, schema: type[T], effort: str = "medium", max_tokens: int = 16000) -> T:
        assert_network("call the OpenAI API")
        kwargs: dict = {}
        if self.reasoning:  # only reasoning models accept this; OPENAI_REASONING=true opts in
            kwargs["reasoning"] = {"effort": effort}
        response = await self.client.responses.parse(
            model=self.model,
            instructions=system,
            input=prompt,
            text_format=schema,
            max_output_tokens=max_tokens,
            **kwargs,
        )
        parsed = response.output_parsed
        if parsed is None:
            refusal = next(
                (c.refusal for item in response.output if getattr(item, "type", "") == "message" for c in getattr(item, "content", []) if getattr(c, "type", "") == "refusal"),
                None,
            )
            raise RuntimeError(f"LLM refused: {refusal}" if refusal else "LLM returned output that did not match the schema")
        return parsed


class NoopLLM:
    enabled = False

    async def structured(self, *, system: str, prompt: str, schema: type[T], effort: str = "medium", max_tokens: int = 16000) -> T:
        raise RuntimeError("LLM is not configured (set OPENAI_API_KEY and NETWORK_ENABLED=true)")


def create_llm() -> LLM:
    s = get_settings()
    if s.openai_api_key and s.network_enabled:
        log.info("llm: OpenAI enabled (%s)", s.openai_model)
        return OpenAILLM(s.openai_model, s.openai_api_key, s.openai_base_url, s.openai_reasoning)
    log.info("llm: disabled (heuristic fallbacks only)")
    return NoopLLM()
