import pytest
import httpx
from unittest.mock import patch, AsyncMock
from aegis.kb.scrapers.blog import BlogScraper
from aegis.kb.scrapers.youtube import YouTubeScraper
from aegis.kb.scrapers.reddit import RedditScraper

@pytest.mark.asyncio
async def test_blog_scraper_success():
    scraper = BlogScraper()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # Mocking a valid HTML response
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><head><title>Test Blog</title></head><body><p>Test content.</p></body></html>"
        mock_get.return_value.raise_for_status = lambda: None
        
        docs = await scraper.get_raw_documents(["http://example.com/blog"])
        assert len(docs) == 1
        assert docs[0].title == "Test Blog"
        assert "Test content." in docs[0].content
        assert docs[0].source_type == "blog"

@pytest.mark.asyncio
async def test_youtube_scraper_success():
    scraper = YouTubeScraper()
    with patch("aegis.kb.scrapers.youtube.YouTubeTranscriptApi.fetch") as mock_fetch, \
         patch("aegis.kb.scrapers.youtube.TextFormatter.format_transcript") as mock_format:
        
        mock_fetch.return_value = ["dummy_transcript"]
        mock_format.return_value = "Hello transcript"
        
        docs = await scraper.get_raw_documents(["https://youtube.com/watch?v=12345678901"])
        assert len(docs) == 1
        assert docs[0].id == "12345678901"
        assert "Hello transcript" in docs[0].content
        assert docs[0].source_type == "youtube"

@pytest.mark.asyncio
async def test_reddit_scraper_httpx_fallback():
    # Test fallback json when no client_id provided
    scraper = RedditScraper(client_id=None, client_secret=None)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json = lambda: [
            {"data": {"children": [{"data": {
                "id": "123", "title": "Test Post", "selftext": "Post content", "author": "test_user", "subreddit": "merval", "score": 10
            }}]}}
        ]
        mock_get.return_value.raise_for_status = lambda: None
        
        docs = await scraper.get_raw_documents(["https://www.reddit.com/r/merval/comments/123/test_post/"])
        assert len(docs) == 1
        assert docs[0].title == "Test Post"
        assert docs[0].content == "Post content"
        assert docs[0].source_type == "reddit"

@pytest.mark.asyncio
async def test_blog_scraper_rate_limit():
    scraper = BlogScraper(max_concurrent=1)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 429
        # The exception triggers inner scraper logic to catch and return None
        docs = await scraper.get_raw_documents(["http://example.com/rate-limited"])
        assert len(docs) == 0
