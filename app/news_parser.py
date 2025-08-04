import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List

import feedparser
import httpx
from email.utils import parsedate_to_datetime

USER_AGENT = "MinimalNewsFetcher/1.0"


def make_external_id(entry: dict) -> str:
    """
    Generate a unique external ID for a feed entry.
    Use 'id' field if present; otherwise, create SHA256 hash
    of concatenated title, link, and published date.
    """
    if entry.get("id"):
        return entry["id"]
    raw = (entry.get("title", "") or "") + (entry.get("link", "") or "") + (entry.get("published", "") or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_date(entry: dict) -> Optional[datetime]:
    """
    Parse published or updated date string from feed entry
    into a timezone-aware datetime object in UTC.
    Returns None if parsing fails or date is missing.
    """
    if entry.get("published"):
        try:
            return parsedate_to_datetime(entry["published"]).astimezone(timezone.utc)
        except Exception:
            pass
    if entry.get("updated"):
        try:
            return parsedate_to_datetime(entry["updated"]).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def normalize_json_feed(parsed_json: dict) -> List[Dict]:
    """
    Normalize JSON Feed (https://jsonfeed.org/) format entries
    into a unified list of dictionaries with expected fields.
    Falls back to current datetime if publication date is missing or invalid.
    """
    items = []
    for item in parsed_json.get("items", []):
        published = item.get("date_published")
        published_dt = None
        if published:
            try:
                # Convert ISO8601 with possible trailing 'Z' to datetime with UTC timezone
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                published_dt = None
        items.append({
            "external_id": item.get("id") or hashlib.sha256((item.get("url", "") or "").encode()).hexdigest(),
            "title": item.get("title", ""),
            "link": item.get("url", ""),
            "author": item.get("author", ""),
            "published": published_dt or datetime.now(timezone.utc),
            "summary": item.get("summary") or item.get("content_text", ""),
            "content": item.get("content_html", ""),
        })
    return items


def normalize_feedparser_entries(parsed) -> List[Dict]:
    """
    Normalize entries parsed by feedparser (RSS/Atom feeds)
    into a list of unified dictionaries with standard keys.
    """
    entries = []
    for entry in parsed.entries:
        dt = parse_date(entry) or datetime.now(timezone.utc)
        content = ""
        if entry.get("content"):
            try:
                content = entry["content"][0].get("value", "")
            except Exception:
                content = ""
        entries.append({
            "external_id": make_external_id(entry),
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "author": entry.get("author", entry.get("dc_creator", "")),
            "published": dt,
            "summary": entry.get("summary", ""),
            "content": content,
        })
    return entries


def fetch_and_normalize(feed_url: str) -> List[Dict]:
    """
    Fetch feed content from URL and normalize it to a list of entries.
    Handles both JSON Feed and RSS/Atom formats.
    Uses httpx client with User-Agent and timeout.
    """
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(follow_redirects=True, headers=headers, timeout=10.0) as client:
        resp = client.get(feed_url)
        resp.raise_for_status()
        text = resp.text

    # Attempt to parse JSON Feed
    try:
        parsed_json = json.loads(text)
        if isinstance(parsed_json, dict) and parsed_json.get("version", "").startswith("https://jsonfeed.org"):
            return normalize_json_feed(parsed_json)
    except json.JSONDecodeError:
        pass

    # Fallback to RSS/Atom parsing via feedparser
    parsed = feedparser.parse(text)
    return normalize_feedparser_entries(parsed)


def get_latest(feed_url: str) -> Optional[Dict]:
    """
    Retrieve the latest news entry from the feed,
    sorted by publication date descending.
    Returns None if no entries found.
    """
    entries = fetch_and_normalize(feed_url)
    if not entries:
        return None

    entries.sort(key=lambda e: e["published"], reverse=True)
    return entries[0]


def get_news(feed_url: str) -> Optional[List[Dict]]:
    """
    Retrieve all news entries from the feed,
    sorted by publication date descending.
    Returns None if no entries found.
    """
    entries = fetch_and_normalize(feed_url)
    if not entries:
        return None

    entries.sort(key=lambda e: e["published"], reverse=True)
    return entries
