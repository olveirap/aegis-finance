import io
from typing import List
from pypdf import PdfReader
import httpx

from aegis.kb.scrapers.base import BaseScraper
from aegis.kb.scrapers.models import RawDocument
from aegis.kb.scrapers.blog import BlogScraper

class RegulationScraper(BaseScraper):
    """
    Scraper for Argentine regulatory documents (HTML and PDF).
    """
    def __init__(self, max_concurrent: int = 5):
        super().__init__(max_concurrent=max_concurrent)
        self.html_scraper = BlogScraper(max_concurrent=max_concurrent)

    async def get_raw_documents(self, urls: List[str]) -> List[RawDocument]:
        documents = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for url in urls:
                if url.lower().endswith(".pdf"):
                    doc = await self._scrape_pdf(client, url)
                else:
                    docs = await self.html_scraper.get_raw_documents([url])
                    doc = docs[0] if docs else None
                    if doc:
                        doc.source_type = "regulation"
                        
                if doc:
                    documents.append(doc)
        return documents

    async def _scrape_pdf(self, client: httpx.AsyncClient, url: str) -> RawDocument | None:
        try:
            response = await self._fetch_url(client, url)
            pdf_data = io.BytesIO(response.content)
            reader = PdfReader(pdf_data)
            
            text_content = ""
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
            
            metadata = reader.metadata
            title = metadata.title if metadata and metadata.title else url

            return RawDocument(
                id=url,
                title=title if title else "PDF Document",
                content=text_content.strip(),
                url=url,
                source_type="regulation",
                author=metadata.author if metadata and metadata.author else None,
                metadata={"pages": len(reader.pages)}
            )
        except Exception as e:
            print(f"Failed to scrape PDF {url}: {e}")
            return None
