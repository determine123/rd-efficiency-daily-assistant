from __future__ import annotations

import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any


def _clean_html(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"<script[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        if _local_name(child.tag) in names:
            return _clean_html(child.text or "")
    return ""


def _item_link(item: ET.Element) -> str:
    for child in list(item):
        name = _local_name(child.tag)
        if name == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
        if name == "guid" and child.text and child.text.startswith("http"):
            return child.text.strip()
    return ""


def _parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return value


def parse_rss(xml_bytes: bytes, feed_url: str = "") -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    feed_title = _child_text(root, {"title"})
    items = [element for element in root.iter() if _local_name(element.tag) in {"item", "entry"}]
    records = []
    for index, item in enumerate(items):
        title = _child_text(item, {"title"})
        url = _item_link(item)
        content = _child_text(item, {"description", "summary", "content", "encoded"})
        source_name = _child_text(item, {"source"}) or feed_title or feed_url
        published = _child_text(item, {"pubdate", "published", "updated", "date"})
        raw = f"{title}\n{url}\n{content}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        records.append({
            "news_id": f"rss_{digest[:16] if digest else index}",
            "title": title,
            "url": url,
            "source_name": source_name,
            "published_at": _parse_date(published),
            "content": content,
            "tags": [],
            "raw_hash": digest,
            "collection_method": "rss",
            "feed_url": feed_url,
        })
    return records


def fetch_rss(url: str, timeout: int = 15, user_agent: str = "R&D-Daily-Report/0.1") -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_rss(response.read(), feed_url=url)


def collect_rss(urls: list[str], timeout: int = 15) -> list[dict[str, Any]]:
    records = []
    errors = []
    for url in urls:
        try:
            records.extend(fetch_rss(url, timeout=timeout))
        except Exception as exc:  # 单个订阅源失败不应阻断日报
            errors.append({"url": url, "error": str(exc)})
    return records
