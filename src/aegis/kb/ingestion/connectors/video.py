# SPDX-License-Identifier: MIT
"""YouTube Video Connectors.

Provides cheap transcript extraction and an expensive Whisper fallback path.
"""

from __future__ import annotations

import hashlib
from typing import AsyncIterator

from youtube_transcript_api import YouTubeTranscriptApi

from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig
from aegis.kb.ontology import SourceType


class VideoConnector(BaseConnector):
    """Fetches transcripts directly via youtube-transcript-api (cheap)."""

    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        
        video_id = config.params.get("video_id")
        playlist_id = config.params.get("playlist_id")
        
        if not video_id and not playlist_id:
             raise ValueError(f"Source '{config.name}' requires a video_id or playlist_id")
        
        # For simplicity, if video_id is provided, fetch single. 
        # Playlist expansion requires Google API or scrapetube (deferred detail).
        video_ids = [video_id] if video_id else []

        for vid in video_ids:
            try:
                # Synchronous call; in real world execute in threadpool
                transcript = YouTubeTranscriptApi.get_transcript(vid, languages=['es', 'en'])
                full_text = " ".join([t['text'] for t in transcript])
                
                raw_bytes = full_text.encode("utf-8")
                bytes_hash = hashlib.sha256(raw_bytes).hexdigest()

                meta = SourceMeta(
                    source_url=f"https://www.youtube.com/watch?v={vid}",
                    source_type=SourceType.VIDEO_WEBINAR,
                    jurisdiction=config.jurisdiction,
                    topic_tags=config.ontology_tags,
                    raw_bytes_hash=bytes_hash,
                )
                
                yield raw_bytes, meta
                
            except Exception as e:
                logger.warning(f"Failed to fetch transcript for {vid}: {e}")


class WhisperVideoConnector(BaseConnector):
    """Downloads audio and uses Whisper via llama.cpp (expensive)."""
    
    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        raise NotImplementedError("Whisper fallback not yet implemented in MVP")
