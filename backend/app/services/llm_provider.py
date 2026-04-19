"""
Abstract LLM provider interface + Ollama implementation using /api/chat.
Switching to /api/chat gives us native system/user/assistant roles
and better compatibility with the OpenAI message format.
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

    def __repr__(self) -> str:
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
    ) -> str:
        """Send messages and return the assistant's response text."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.3,
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
    ) -> str:
        """Legacy convenience method — builds a simple 1-2 message chat."""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        return await self.chat(messages)


# ─── Ollama /api/chat provider ─────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """LLM provider using Ollama's /api/chat endpoint."""

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
    ) -> str:
        """Call Ollama /api/chat and return the full response."""
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

        logger.debug("Ollama chat request", model=payload["model"], messages=len(messages))

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error("Ollama error", status=resp.status, body=error_body)
                        raise RuntimeError(f"Ollama returned {resp.status}: {error_body}")
                    data = await resp.json()
                    content = data.get("message", {}).get("content", "")
                    logger.debug(
                        "Ollama response received",
                        model=payload["model"],
                        tokens=data.get("eval_count"),
                        content_length=len(content),
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
    ) -> AsyncGenerator[str, None]:
        """Stream Ollama /api/chat responses token by token."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

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
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                return
                        except json.JSONDecodeError:
                            continue

        except aiohttp.ClientError as e:
            logger.error("Ollama stream connection error", error=str(e))
            raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}: {e}") from e