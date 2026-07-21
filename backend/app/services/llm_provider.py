"""
Abstract LLM provider interface + OpenAI-compatible implementation.
Uses the standard /v1/chat/completions endpoint (compatible with OpenAI,
OpenRouter, Together AI, and any custom provider).
Supports JSON mode via response_format and streaming via SSE.
"""

import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Optional

import aiohttp

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Message types ──────────────────────────────────────────────────────────

class Message:
    """A single message in a chat conversation."""

    def __init__(self, role: str, content: str):
        self.role = role  # "system" | "user" | "assistant"
        self.content = content

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    def __repr__(self):
        return f"Message({self.role!r}, {self.content[:80]}...)"


# ─── Abstract provider ─────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Base class for all LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        format_json: bool = False,
        think: Optional[bool] = None,
    ) -> str:
        """Send messages and return the assistant's response text."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        think: Optional[bool] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream the assistant's response token by token."""
        ...
        # Make this an async generator
        if False:
            yield  # pragma: no cover

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        think: Optional[bool] = None,
    ) -> str:
        """Legacy convenience method — builds a simple 1-2 message chat."""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        return await self.chat(messages, think=think)


# ─── OpenAI-compatible /v1/chat/completions provider ───────────────────────

class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI-compatible /v1/chat/completions endpoint.

    Works with:
      - OpenAI          (https://api.openai.com/v1)
      - OpenRouter      (https://openrouter.ai/api/v1)
      - Together AI     (https://api.together.xyz/v1)
      - Any custom provider implementing the same API shape.

    Authentication is via Bearer token in the Authorization header.
    Supports JSON mode (response_format={"type": "json_object"}).
    The 'think' parameter is accepted for interface compatibility but ignored
    (OpenAI doesn't have a generic 'think' parameter; reasoning models like
     o1/o3 use a different API contract).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key or ""
        self.model = model or settings.openai_model

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        format_json: bool = False,
        think: Optional[bool] = None,
    ) -> str:
        """Call /v1/chat/completions and return the response content.

        Args:
            messages: Chat messages (system, user, assistant).
            model: Override the default model name.
            temperature: Sampling temperature (0.0 = deterministic).
            format_json: Request JSON-formatted output via response_format.
            think: Ignored — kept for interface compatibility with Ollama.
        """
        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if format_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.debug(
            "OpenAI-compatible chat request",
            url=url,
            model=payload["model"],
            messages=len(messages),
            format_json=format_json,
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error(
                            "LLM API error",
                            status=resp.status,
                            body=error_body,
                            url=url,
                        )
                        raise RuntimeError(
                            f"LLM API returned {resp.status} from {url}: {error_body}"
                        )
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError(
                            f"LLM API returned empty choices from {url}: {json.dumps(data)[:500]}"
                        )
                    content = choices[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    logger.debug(
                        "LLM response received",
                        model=payload["model"],
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        content_length=len(content),
                    )
                    return content

        except aiohttp.ClientError as e:
            logger.error("LLM API connection error", error=str(e), url=url)
            raise RuntimeError(
                f"Cannot connect to LLM API at {self.base_url}: {e}"
            ) from e

    async def chat_stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        think: Optional[bool] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream /v1/chat/completions responses token by token (SSE).

        Yields content delta tokens as they arrive.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise RuntimeError(
                            f"LLM API returned {resp.status}: {error_body}"
                        )

                    # Parse SSE stream: "data: {...}\n\n"
                    buffer = ""
                    async for chunk in resp.content:
                        buffer += chunk.decode("utf-8")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            if line == "data: [DONE]":
                                return
                            if line.startswith("data: "):
                                json_str = line[6:]
                                try:
                                    data = json.loads(json_str)
                                    delta = (
                                        data.get("choices", [{}])[0]
                                        .get("delta", {})
                                        .get("content", "")
                                    )
                                    if delta:
                                        yield delta
                                except json.JSONDecodeError:
                                    continue

        except aiohttp.ClientError as e:
            logger.error("LLM stream connection error", error=str(e))
            raise RuntimeError(
                f"Cannot connect to LLM API at {self.base_url}: {e}"
            ) from e


# ─── Convenience alias ────────────────────────────────────────────────────

# Keep OllamaProvider as an alias for backward compatibility during migration
# Will be removed in a future version
OllamaProvider = OpenAIProvider
