import logging
import re
from typing import List

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import Article

RSS_URL = "https://www.chinapress.com.my/feed/"
HOME_URL = "https://www.chinapress.com.my/"

def _extract_images_from_feed_entry(entry) -> List[str]:
    images: List[str] = []
    try:
        for media in entry.get("media_content", []) or []:
            url = media.get("url")
            if url:
                images.append(url)
    except Exception:
        pass
    try:
        for link in entry.get("links", []) or []:
            if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image/"):
                href = link.get("href")
                if href:
                    images.append(href)
    except Exception:
        pass
    try:
        summary = entry.get("summary", "")
        for m in re.finditer(r"<img[^>]+src=\"([^\"]+)\"", summary):
            images.append(m.group(1))
    except Exception:
        pass
    seen = set()
    unique = []
    for u in images:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique

def fetch_from_rss(max_items: int = 50) -> List[Article]:
    logging.info("Fetching RSS: %s", RSS_URL)
    fp = feedparser.parse(RSS_URL)
    articles: List[Article] = []
    for entry in fp.entries[:max_items]:
        url = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not url or not title:
            continue
        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        summary = getattr(entry, "summary", None)
        images = _extract_images_from_feed_entry(entry)
        articles.append(Article(title=title.strip(), url=url.strip(), published_at=published, summary=summary, images=images))
    return articles

def fetch_from_home(max_items: int = 30) -> List[Article]:
    logging.info("Fetching homepage HTML: %s", HOME_URL)
    resp = requests.get(HOME_URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles: List[Article] = []
    for node in soup.select("article, .post, .jeg_post, .entry-header, h3.jeg_post_title, h2.entry-title"):
        a = node.find("a")
        if not a or not a.get("href"):
            continue
        url = a["href"].strip()
        title = (a.get_text() or "").strip()
        if not title:
            heading = node.find(["h2", "h3"]) or node
            title = (heading.get_text() or "").strip()
        if not title or not url:
            continue

        img_src = None
        img = node.find("img")
        if img and img.get("src"):
            img_src = img["src"].strip()

        images = [img_src] if img_src else []
        articles.append(Article(title=title, url=url, published_at=None, summary=None, images=images))
        if len(articles) >= max_items:
            break

    seen = set()
    unique: List[Article] = []
    for art in articles:
        if art.url in seen:
            continue
        seen.add(art.url)
        unique.append(art)
    return unique

def fetch_latest(max_items: int = 50) -> List[Article]:
    try:
        rss_items = fetch_from_rss(max_items=max_items)
        if rss_items:
            return rss_items
    except Exception as e:
        logging.warning("RSS fetch failed: %s", e)
    try:
        return fetch_from_home(max_items=max_items)
    except Exception as e:
        logging.error("Homepage fetch failed: %s", e)
        return []
