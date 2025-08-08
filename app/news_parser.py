import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List

import feedparser
import httpx
from email.utils import parsedate_to_datetime

USER_AGENT = "MinimalNewsFetcher/1.0"




async def get_latest(rss_url: str) -> Optional[Dict]:
    """
    Fetch the latest news item from the given RSS feed URL and return it as a JSON-serializable dict.
    Returns None if no items are found or on error.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(rss_url, headers=headers)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
    except Exception:
        return None

    if not feed.entries:
        return None

    # Find the latest entry by published/updated date if available, else take the first
    def get_entry_datetime(entry):
        dt = None
        if "published" in entry:
            try:
                dt = parsedate_to_datetime(entry.published)
            except Exception:
                pass
        if not dt and "updated" in entry:
            try:
                dt = parsedate_to_datetime(entry.updated)
            except Exception:
                pass
        return dt or datetime.now(timezone.utc)

    latest_entry = max(feed.entries, key=get_entry_datetime)

    # Prepare JSON-serializable dict
    result = {
        "title": latest_entry.get("title", ""),
        "link": latest_entry.get("link", ""),
        "summary": latest_entry.get("summary", "") or latest_entry.get("description", ""),
        "published": latest_entry.get("published", ""),
        "id": latest_entry.get("id", latest_entry.get("link", "")),
    }
    return result
