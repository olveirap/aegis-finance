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
            # Using tenacity for automatic retries
            retryer = AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
                reraise=True,
            )
            
            async for attempt in retryer:
                with attempt:
                    logger.debug(f"Requesting {method} {url} (attempt {attempt.retry_state.attempt_number})")
                    response = await self.client.request(method, url, **kwargs)
                    
                    # Raise for 4xx and 5xx. If we get a 404, we usually don't want to retry, 
                    # but tenacity will retry on HTTPStatusError unless we configure it.
                    # As a default wrapper, we raise; callers can catch if 404 is expected.
                    if response.status_code >= 500 or response.status_code == 429:
                        response.raise_for_status()
                    return response
            
            # This should not be hit due to reraise=True in generic cases
            raise RuntimeError(f"Failed to complete {method} {url}")

    async def aclose(self) -> None:
        """Closes the underlying httpx.AsyncClient."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
