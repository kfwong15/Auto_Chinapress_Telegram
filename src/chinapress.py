import logging
import re
from typing import List

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
try:
    # Optional dependency; used as a dynamic-rendering fallback
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover
    sync_playwright = None  # type: ignore

from .models import Article

RSS_URL = "https://www.chinapress.com.my/feed/"
HOME_URL = "https://www.chinapress.com.my/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": HOME_URL,
    "Connection": "keep-alive",
}

def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=[403, 429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

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
    # feedparser supports sending custom request headers to avoid being blocked
    fp = feedparser.parse(RSS_URL, request_headers={
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
    })
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
    session = _create_session()
    resp = session.get(HOME_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Fallback strategy: scan all anchor tags and pick article-like URLs
    anchors = soup.select("a[href]")
    articles: List[Article] = []
    seen_urls: set[str] = set()
    for a in anchors:
        href_raw = a.get("href")
        if not href_raw:
            continue
        url = href_raw.strip()
        # Only keep links to the same domain
        if "chinapress.com.my" not in url:
            continue
        # Filter out navigational/category links by requiring article-like patterns
        is_post_id = bool(re.search(r"[?&]p=\\d+", url))
        is_yyyy_mm_dd = bool(re.search(r"/20\\d{2}/\\d{1,2}/\\d{1,2}/", url))
        is_yyyymmdd = bool(re.search(r"/20\\d{2}\\d{2}\\d{2}/", url))
        if not (is_post_id or is_yyyy_mm_dd or is_yyyymmdd):
            continue
        title = (a.get_text() or "").strip()
        if len(title) < 6:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append(Article(title=title, url=url, published_at=None, summary=None, images=[]))
        if len(articles) >= max_items:
            break

    return articles

def fetch_from_home_playwright(max_items: int = 30) -> List[Article]:
    if sync_playwright is None:
        logging.warning("Playwright not available; skipping dynamic rendering fallback.")
        return []
    logging.info("Fetching homepage via Playwright: %s", HOME_URL)
    articles: List[Article] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS["User-Agent"],
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto(HOME_URL, wait_until="load", timeout=30000)
            # Heuristic: WordPress-style article URLs containing year/month/day
            anchors = page.query_selector_all("a[href]")
            seen_urls = set()
            for a in anchors:
                href = (a.get_attribute("href") or "").strip()
                if not href or not href.startswith("http"):
                    continue
                # Normalize to main domain only
                if "chinapress.com.my" not in href:
                    continue
                # Match /YYYY/MM/DD/ patterns
                if not re.search(r"/20\\d{2}/\\d{1,2}/\\d{1,2}/", href):
                    continue
                title = (a.inner_text() or "").strip()
                if len(title) < 6:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                # Try to find a nearby image
                img_src: str | None = None
                try:
                    # Look up the DOM for a container with an image
                    container = a.evaluate_handle("el => el.closest('article, .post, .jeg_post, .entry')")
                    if container:
                        img = a.page.query_selector("article img, .post img, .jeg_post img, .entry img")
                        if img:
                            src = img.get_attribute("src")
                            if src:
                                img_src = src.strip()
                except Exception:
                    pass
                images = [img_src] if img_src else []
                articles.append(Article(title=title, url=href, published_at=None, summary=None, images=images))
                if len(articles) >= max_items:
                    break
            context.close()
            browser.close()
    except Exception as e:
        logging.error("Playwright fetch failed: %s", e)
        return []
    return articles

def fetch_latest(max_items: int = 50) -> List[Article]:
    try:
        rss_items = fetch_from_rss(max_items=max_items)
        if rss_items:
            return rss_items
    except Exception as e:
        logging.warning("RSS fetch failed: %s", e)
    try:
        items = fetch_from_home(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("Homepage fetch failed: %s", e)
    # Last resort: dynamic rendering
    try:
        items = fetch_from_home_playwright(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("Homepage (Playwright) fetch failed: %s", e)
    return []
