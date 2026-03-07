import abc
from typing import List
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import httpx

from aegis.kb.scrapers.models import RawDocument

class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass

class RateLimitError(ScraperError):
    """Exception raised when hitting rate limits."""
    pass

class BaseScraper(abc.ABC):
    """
    Abstract base class for all KB source scrapers.
    """
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    @abc.abstractmethod
    async def get_raw_documents(self, *args, **kwargs) -> List[RawDocument]:
        """
        Fetch documents from the source. Needs implementation by subclasses.
        """
        pass

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, RateLimitError))
    )
    async def _fetch_url(self, client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
        """
        Helper method to fetch a URL safely with retries and rate limiting respect.
        """
        async with self.semaphore:
            response = await client.get(url, **kwargs)
            if response.status_code == 429:
                raise RateLimitError(f"Rate limited on {url}")
            response.raise_for_status()
            return response
