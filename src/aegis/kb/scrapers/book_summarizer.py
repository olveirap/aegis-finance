import re
import os
from typing import List

from aegis.kb.scrapers.base import BaseScraper
from aegis.kb.scrapers.models import RawDocument

class BookSummarizerScraper(BaseScraper):
    """
    Scraper for structured book notes (Markdown/Text).
    Extracts 'Tips & Rules' and ignores general full text to avoid copyright issues.
    """
    def __init__(self, max_concurrent: int = 5):
        super().__init__(max_concurrent=max_concurrent)

    async def get_raw_documents(self, file_paths: List[str]) -> List[RawDocument]:
        documents = []
        for path in file_paths:
            if not os.path.exists(path):
                print(f"File not found: {path}")
                continue
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract bullet points, blockquotes or lines with "Tip/Rule/Regla:"
                # This is a naive heuristic for "structured tips" without LLM
                extracted_lines = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith(('-', '*')) or re.search(r'^(tip|rule|regla|nota|importante):', line, re.IGNORECASE):
                        extracted_lines.append(line)
                
                if not extracted_lines:
                    continue
                
                summarized_content = "\n".join(extracted_lines)
                title = os.path.basename(path).split('.')[0].replace('_', ' ').title()
                
                doc = RawDocument(
                    id=path,
                    title=f"Notes: {title}",
                    content=summarized_content,
                    url=f"file://{os.path.abspath(path)}",
                    source_type="book_notes"
                )
                documents.append(doc)
            except Exception as e:
                print(f"Failed to process book notes {path}: {e}")
        
        return documents
