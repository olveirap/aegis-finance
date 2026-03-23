# SPDX-License-Identifier: MIT
"""Shared HTTP client wrapper for ingestion and market adapters.

Provides configurable resilience (retries via logging, exponential backoff)
and rate-limiting (via asyncio.Semaphore).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import httpx


logger = logging.getLogger(__name__)


class ResilientHTTPClient:
    """A resilient HTTP client wrapping httpx.AsyncClient.

    Features:
      - Configurable rate limiting via asyncio.Semaphore
      - Configurable retries via tenacity
      - Follows redirects
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 3,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = headers or {}

        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy initialization of the underlying httpx client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=True,
            )
        return self._client

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Performs a GET request with rate limiting and retries."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Performs a POST request with rate limiting and retries."""
        return await self.request("POST", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Generic request execution with the configured resilience."""
        async with self.semaphore:

            def should_retry(exc: BaseException) -> bool:
                return isinstance(
                    exc, httpx.HTTPStatusError
                ) and exc.response.status_code in {
                    408,
                    429,
                } | set(range(500, 600))

            # Using tenacity for automatic retries
            retryer = AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(
                    (httpx.RequestError, httpx.TimeoutException)
                )
                | retry_if_exception(should_retry),
                reraise=True,
            )

            async for attempt in retryer:
                with attempt:
                    logger.debug(
                        "Requesting %s %s (attempt %s)",
                        method,
                        url,
                        attempt.retry_state.attempt_number,
                    )
                    response = await self.client.request(method, url, **kwargs)

                    if response.status_code >= 400:
                        response.raise_for_status()
                    return response

            # This should not be hit due to reraise=True in generic cases
            raise RuntimeError(f"Failed to complete {method} {url}")

    async def aclose(self) -> None:
        """Closes the underlying httpx.AsyncClient."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
