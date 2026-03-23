# SPDX-License-Identifier: MIT
"""Provider-agnostic Cloud LLM client with local fallback.

Supports OpenAI, Anthropic, and Gemini. If cloud is disabled or API keys are
missing, it falls back to the local llama.cpp server.
"""

from __future__ import annotations

import logging

import httpx
from openai import AsyncOpenAI

from aegis.config import get_config, LLMConfig

logger = logging.getLogger(__name__)


class CloudLLMClient:
    """Orchestrates calls to cloud LLMs with local fallback."""

    def __init__(self) -> None:
        self.config: LLMConfig = get_config().llm
        self.client: AsyncOpenAI | None = None

        if self.config.cloud.enabled and self.config.cloud.api_key:
            if self.config.cloud.provider == "openai":
                self.client = AsyncOpenAI(api_key=self.config.cloud.api_key)
            # Add other providers here as needed

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Generate a response using cloud LLM or local fallback.

        Args:
            system_prompt: System instructions.
            user_prompt: User query or context.
            temperature: Sampling temperature.
            response_format: Optional dict for structured output (e.g. {"type": "json_object"}).

        Returns:
            The generated text response.
        """
        if self.client and self.config.cloud.enabled:
            try:
                return await self._call_cloud(
                    system_prompt, user_prompt, temperature, response_format
                )
            except Exception as e:
                logger.warning("Cloud LLM call failed: %s. Falling back to local.", e)

        return await self._call_local(
            system_prompt, user_prompt, temperature, response_format
        )

    async def _call_cloud(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Call the configured cloud provider."""
        # Currently only OpenAI is fully implemented as an example
        if self.config.cloud.provider == "openai":
            # Filter None to avoid API errors if not provided
            kwargs = {"response_format": response_format} if response_format else {}
            resp = await self.client.chat.completions.create(
                model=self.config.cloud.model,  # Default or from config
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                **kwargs,
            )
            return resp.choices[0].message.content or ""

        raise NotImplementedError(
            f"Cloud provider '{self.config.cloud.provider}' not implemented."
        )

    async def _call_local(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Call the local llama.cpp server."""
        url = self.config.local.llama_cpp_server
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": self.config.local.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
