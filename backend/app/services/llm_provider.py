"""
Abstract LLM provider interface + Ollama implementation using /api/chat.
Switching to /api/chat gives us native system/user/assistant roles
and better compatibility with the OpenAI message format.
Supports Ollama's "think" parameter for reasoning-capable models.
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


# ─── Ollama /api/chat provider ─────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """LLM provider using Ollama's /api/chat endpoint.

    Supports the 'think' parameter for reasoning-capable models
    (deepseek-v3.2, qwen3.5, mistral-large-3, gpt-oss, kimi-k2, etc).
    When think=True, the model produces a thinking trace before the answer.
    When think=False, the model responds directly (faster, for draft passes).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        format_json: bool = False,
        think: Optional[bool] = None,
    ) -> str:
        """Call Ollama /api/chat and return the full response.

        Args:
            messages: Chat messages (system, user, assistant).
            model: Override the default model.
            temperature: Sampling temperature.
            format_json: Request JSON-formatted output.
            think: Enable/disable thinking mode for reasoning models.
                   None = don't send the parameter (model default).
                   True = model thinks before answering (slower, better for refine).
                   False = model answers directly (faster, for draft passes).
        """
        url = f"{self.base_url}/api/chat"
        payload: dict = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if format_json:
            payload["format"] = "json"
        if think is not None:
            payload["think"] = think

        logger.debug("Ollama chat request", model=payload["model"], messages=len(messages), think=think)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error("Ollama error", status=resp.status, body=error_body)
                        raise RuntimeError(f"Ollama returned {resp.status}: {error_body}")
                    data = await resp.json()
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    # Log thinking trace if present (for debugging / refine pass)
                    thinking = msg.get("thinking")
                    if thinking:
                        logger.debug(
                            "Ollama thinking trace",
                            model=payload["model"],
                            thinking_length=len(thinking),
                        )
                    logger.debug(
                        "Ollama response received",
                        model=payload["model"],
                        tokens=data.get("eval_count"),
                        content_length=len(content),
                        had_thinking=bool(thinking),
                    )
                    return content

        except aiohttp.ClientError as e:
            logger.error("Ollama connection error", error=str(e))
            raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e

    async def chat_stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
        think: Optional[bool] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream Ollama /api/chat responses token by token.

        Note: thinking tokens are not yielded — only content tokens.
        This keeps the streaming output clean for consumers.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if think is not None:
            payload["think"] = think

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        raise RuntimeError(f"Ollama returned {resp.status}: {error_body}")

                    async for line in resp.content:
                        line_text = line.decode("utf-8").strip()
                        if not line_text:
                            continue
                        try:
                            chunk = json.loads(line_text)
                            msg = chunk.get("message", {})
                            # Yield content tokens only (skip thinking tokens in stream)
                            token = msg.get("content", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                return
                        except json.JSONDecodeError:
                            continue

        except aiohttp.ClientError as e:
            logger.error("Ollama stream connection error", error=str(e))
            raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e