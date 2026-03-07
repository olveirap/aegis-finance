import re
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from aegis.kb.scrapers.base import BaseScraper
from aegis.kb.scrapers.models import RawDocument

class YouTubeScraper(BaseScraper):
    """
    Scraper for YouTube transcripts.
    """
    def __init__(self, languages: List[str] = ['es', 'en'], max_concurrent: int = 5):
        super().__init__(max_concurrent=max_concurrent)
        self.languages = languages
        self.formatter = TextFormatter()

    def _extract_video_id(self, url: str) -> str | None:
        """Extracts the video ID from a YouTube URL."""
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        return match.group(1) if match else None

    async def get_raw_documents(self, urls: List[str]) -> List[RawDocument]:
        documents = []
        for url in urls:
            video_id = self._extract_video_id(url)
            if not video_id:
                print(f"Invalid YouTube URL: {url}")
                continue
            
            try:
                # Fetch transcript using the instance method
                api = YouTubeTranscriptApi()
                transcript = api.fetch(video_id, languages=self.languages)
                text_content = self.formatter.format_transcript(transcript)

                doc = RawDocument(
                    id=video_id,
                    title=f"YouTube Video {video_id}", # Needs Title extraction if we want but transcript API is just transcripts
                    content=text_content,
                    url=url,
                    source_type="youtube"
                )
                documents.append(doc)
            except Exception as e:
                print(f"Failed to fetch transcript for {url}: {e}")
        
        return documents
