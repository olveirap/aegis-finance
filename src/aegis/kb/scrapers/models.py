from datetime import datetime, timezone
from typing import Optional, Dict

from pydantic import BaseModel, Field

class RawDocument(BaseModel):
    id: str = Field(description="Unique identifier for the document, e.g., URL or distinct ID")
    title: str = Field(description="Title of the document")
    content: str = Field(description="Raw text content of the document")
    url: str = Field(description="Source URL")
    source_type: str = Field(description="Type of source (e.g., blog, reddit, youtube, regulation, book)")
    author: Optional[str] = Field(default=None, description="Author or creator of the content")
    published_at: Optional[datetime] = Field(default=None, description="Publish date of the content")
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the document was scraped")
    metadata: Dict = Field(default_factory=dict, description="Additional source-specific metadata")
