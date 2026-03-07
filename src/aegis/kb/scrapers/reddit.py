import os
import json
from typing import List
import asyncpraw
import httpx
from bs4 import BeautifulSoup

from aegis.kb.scrapers.base import BaseScraper
from aegis.kb.scrapers.models import RawDocument

class RedditScraper(BaseScraper):
    """
    Scraper for Reddit posts and wikis.
    Uses asyncpraw if REDDIT_CLIENT_ID is set, else falls back to httpx parsing.
    """
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, user_agent: str | None = None, max_concurrent: int = 5):
        super().__init__(max_concurrent=max_concurrent)
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.environ.get("REDDIT_USER_AGENT", "python:aegis-finance:0.1 (by /u/aegis-bot)")
        
        self.use_praw = bool(self.client_id and self.client_secret)
        self.reddit = None
        if self.use_praw:
            self.reddit = asyncpraw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent
            )

    async def get_raw_documents(self, urls: List[str]) -> List[RawDocument]:
        documents = []
        for url in urls:
            try:
                if "/wiki/" in url:
                    doc = await self._scrape_wiki(url)
                else:
                    doc = await self._scrape_submission(url)
                
                if doc:
                    documents.append(doc)
            except Exception as e:
                print(f"Failed to scrape Reddit URL {url}: {e}")
        
        return documents
    
    async def _scrape_submission(self, url: str) -> RawDocument | None:
        if self.use_praw:
            submission = await self.reddit.submission(url=url)
            await submission.load()
            content = getattr(submission, 'selftext', '')
            return RawDocument(
                id=submission.id,
                title=submission.title,
                content=content,
                url=url,
                source_type="reddit",
                author=submission.author.name if submission.author else "[deleted]",
                metadata={"subreddit": submission.subreddit.display_name, "score": submission.score}
            )
        else:
            json_url = url.rstrip('/') + ".json"
            headers = {"User-Agent": self.user_agent}
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await self._fetch_url(client, json_url)
                data = resp.json()
                post_data = data[0]["data"]["children"][0]["data"]
                return RawDocument(
                    id=post_data.get("id", url),
                    title=post_data.get("title", ""),
                    content=post_data.get("selftext", ""),
                    url=url,
                    source_type="reddit",
                    author=post_data.get("author", "[deleted]"),
                    metadata={"subreddit": post_data.get("subreddit", ""), "score": post_data.get("score", 0)}
                )

    async def _scrape_wiki(self, url: str) -> RawDocument | None:
        parts = url.rstrip('/').split('/')
        if 'r' not in parts or 'wiki' not in parts:
            return None
        
        subreddit_name = parts[parts.index('r') + 1]
        wiki_page_name = parts[-1] if parts[-1] != 'wiki' else 'index'
        
        if self.use_praw:
            subreddit = await self.reddit.subreddit(subreddit_name)
            wiki_page = await subreddit.wiki.get_page(wiki_page_name)
            return RawDocument(
                id=f"wiki_{subreddit_name}_{wiki_page_name}",
                title=f"r/{subreddit_name} Wiki: {wiki_page_name}",
                content=getattr(wiki_page, 'content_md', ''),
                url=url,
                source_type="reddit",
                metadata={"subreddit": subreddit_name}
            )
        else:
            headers = {"User-Agent": self.user_agent}
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await self._fetch_url(client, url)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                content_div = soup.find('div', class_='md')
                content = content_div.get_text(separator='\n', strip=True) if content_div else soup.get_text(separator=' ', strip=True)
                
                return RawDocument(
                    id=f"wiki_{subreddit_name}_{wiki_page_name}",
                    title=f"r/{subreddit_name} Wiki: {wiki_page_name}",
                    content=content,
                    url=url,
                    source_type="reddit",
                    metadata={"subreddit": subreddit_name}
                )
