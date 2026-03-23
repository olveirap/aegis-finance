# SPDX-License-Identifier: MIT
"""Reddit Connector.

Wrapper around praw to fetch subreddit posts or search results.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import AsyncIterator

import praw

from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig
from aegis.kb.ontology import SourceType


class RedditConnector(BaseConnector):
    """Fetches text content from Reddit (subreddits or search)."""

    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "AegisFinance/1.0")

        if not (client_id and client_secret):
            raise ValueError(
                f"Source '{config.name}' requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET"
            )

        reddit = praw.Reddit(
            client_id=client_id, client_secret=client_secret, user_agent=user_agent
        )

        try:
            subreddit_name = config.params.get("subreddit", "merval")
            limit = config.params.get("limit", 100)

            def get_submissions():
                subreddit = reddit.subreddit(subreddit_name)
                return list(subreddit.hot(limit=limit))

            submissions = await asyncio.to_thread(get_submissions)

            for submission in submissions:
                doc_dict = {
                    "title": submission.title,
                    "selftext": submission.selftext,
                    "url": submission.url,
                    "author": str(submission.author)
                    if submission.author
                    else "deleted",
                    "created_utc": submission.created_utc,
                    "score": submission.score,
                }

                raw_bytes = json.dumps(doc_dict).encode("utf-8")
                bytes_hash = hashlib.sha256(raw_bytes).hexdigest()

                meta = SourceMeta(
                    source_url=f"https://reddit.com{submission.permalink}",
                    source_type=SourceType.REDDIT,
                    jurisdiction=config.jurisdiction,
                    topic_tags=config.ontology_tags,
                    raw_bytes_hash=bytes_hash,
                )

                yield raw_bytes, meta

        finally:
            pass
