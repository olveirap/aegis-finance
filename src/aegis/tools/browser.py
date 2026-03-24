# SPDX-License-Identifier: MIT
"""Privacy-preserving browser tool with strict domain whitelisting.

Extracts content from whitelisted domains using Trafilatura.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import trafilatura

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist Configuration
# ---------------------------------------------------------------------------

WHITELISTED_DOMAINS = {
    "bcra.gob.ar",
    "afip.gob.ar",
    "byma.com.ar",
    "ambito.com",
    "cronista.com",
    "argentina.gob.ar",
    "lanacion.com.ar",
    "infobae.com",
}


def is_whitelisted(url: str) -> bool:
    """Check if a URL belongs to a whitelisted domain."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove 'www.' if present
        if domain.startswith("www."):
            domain = domain[4:]

        # Check for exact match or subdomain match
        for allowed in WHITELISTED_DOMAINS:
            if domain == allowed or domain.endswith("." + allowed):
                return True
        return False
    except Exception:
        return False


async def browse_url(url: str) -> str | None:
    """Extract text content from a whitelisted URL.

    Args:
        url: The URL to browse.

    Returns:
        Cleaned text content or None if not whitelisted or failed.
    """
    if not is_whitelisted(url):
        logger.warning("Attempted to browse non-whitelisted domain: %s", url)
        return None

    logger.info("Browsing: %s", url)

    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return None

        result = trafilatura.extract(
            downloaded, include_comments=False, include_tables=True
        )
        return result
    except Exception as e:
        logger.error("Browsing failed for %s: %s", url, e)
        return None
