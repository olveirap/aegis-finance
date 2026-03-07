import httpx
from typing import List
from bs4 import BeautifulSoup
import trafilatura

from aegis.kb.scrapers.base import BaseScraper
from aegis.kb.scrapers.models import RawDocument


class BlogScraper(BaseScraper):
    """
    Scraper for HTML blogs and articles.
    """
    def __init__(self, max_concurrent: int = 5):
        super().__init__(max_concurrent=max_concurrent)

    async def get_raw_documents(self, urls: List[str]) -> List[RawDocument]:
        documents = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            for url in urls:
                doc = await self._scrape_single_url(client, url)
                if doc:
                    documents.append(doc)
        return documents

    async def _scrape_single_url(self, client: httpx.AsyncClient, url: str) -> RawDocument | None:
        try:
            response = await self._fetch_url(client, url)
            html_content = response.text
            
            # Using trafilatura for main content extraction
            extracted_text = trafilatura.extract(html_content, favor_precision=True)
            
            # Fallback to BeautifulSoup if trafilatura fails
            if not extracted_text:
                soup = BeautifulSoup(html_content, "html.parser")
                extracted_text = soup.get_text(separator=' ', strip=True)

            if not extracted_text:
                return None

            # Title extraction
            metadata = trafilatura.extract_metadata(html_content)
            title = metadata.title if metadata and metadata.title else url
            author = metadata.author if metadata and metadata.author else None

            doc = RawDocument(
                id=url,
                title=title,
                content=extracted_text,
                url=url,
                source_type="blog",
                author=author,
                metadata={"status_code": response.status_code}
            )
            return doc
        except Exception as e:
            print(f"Failed to scrape {url}: {e}")
            return None
