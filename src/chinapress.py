import logging
import re
from typing import List
import xml.etree.ElementTree as ET

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
WP_JSON_POSTS = f"{HOME_URL.rstrip('/')}/wp-json/wp/v2/posts"
SITEMAP_INDEX = f"{HOME_URL.rstrip('/')}/sitemap_index.xml"
POST_SITEMAP = f"{HOME_URL.rstrip('/')}/post-sitemap.xml"

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
        is_post_id = bool(re.search(r"[?&]p=\d+", url))
        is_yyyy_mm_dd = bool(re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", url))
        is_yyyymmdd = bool(re.search(r"/20\d{2}\d{2}\d{2}/", url))
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
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ])
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS["User-Agent"],
                locale="zh-CN",
            )
            page = context.new_page()
            # Reduce headless fingerprint
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """)
            page.goto(HOME_URL, wait_until="load", timeout=30000)
            try:
                page.wait_for_selector("a[href*='?p='], a[href*='/202']", state="attached", timeout=5000)
            except Exception:
                page.wait_for_timeout(2000)
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
                if not re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", href):
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

def fetch_from_wpjson(max_items: int = 30) -> List[Article]:
    """Fetch latest posts via WordPress REST API as a robust fallback.

    Many WordPress sites expose /wp-json/wp/v2/posts which returns JSON
    including links and titles. This often bypasses homepage anti-bot markup
    changes and yields recent posts reliably.
    """
    logging.info("Fetching via WP JSON: %s", WP_JSON_POSTS)
    session = _create_session()
    params = {
        "per_page": min(max_items, 50),
        "page": 1,
        "orderby": "date",
        "order": "desc",
        "_fields": "link,title,excerpt,date",
    }
    resp = session.get(WP_JSON_POSTS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    articles: List[Article] = []
    for item in data:
        link = (item.get("link") or "").strip()
        title_html = ((item.get("title") or {}).get("rendered") or "").strip()
        if not link or not title_html:
            continue
        # Strip HTML from title
        title_text = BeautifulSoup(title_html, "html.parser").get_text().strip()
        if not title_text:
            continue
        articles.append(Article(title=title_text, url=link, published_at=item.get("date"), summary=None, images=[]))
        if len(articles) >= max_items:
            break
    return articles

def fetch_latest(max_items: int = 50) -> List[Article]:
    try:
        rss_items = fetch_from_rss(max_items=max_items)
        if rss_items:
            return rss_items
    except Exception as e:
        logging.warning("RSS fetch failed: %s", e)
    # Try sitemap-based fallback first as it is lightweight and reliable
    try:
        items = fetch_from_sitemap(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("Sitemap fetch failed: %s", e)
    try:
        items = fetch_from_home(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("Homepage fetch failed: %s", e)
    # Next: WordPress REST API fallback
    try:
        items = fetch_from_wpjson(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("WP JSON fetch failed: %s", e)
    # Last resort: dynamic rendering
    try:
        items = fetch_from_home_playwright(max_items=max_items)
        if items:
            return items
    except Exception as e:
        logging.error("Homepage (Playwright) fetch failed: %s", e)
    return []

def fetch_from_sitemap(max_items: int = 30) -> List[Article]:
    """Parse WordPress sitemaps to retrieve latest posts.

    Strategy:
    1. Try post-sitemap.xml directly
    2. If not present, parse sitemap_index.xml to find the newest post sitemap
    """
    logging.info("Fetching via Sitemap: %s or %s", POST_SITEMAP, SITEMAP_INDEX)
    session = _create_session()

    # Helper to parse a given sitemap URL for <url><loc> entries
    def _parse_sitemap_urls(url: str) -> List[str]:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        # Some servers return HTML; try to parse regardless
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return []
        ns_urlset = "{http://www.sitemaps.org/schemas/sitemap/0.9}url"
        urls: List[str] = []
        for url_node in root.findall(f".//{ns_urlset}"):
            loc = url_node.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if loc and "chinapress.com.my" in loc:
                urls.append(loc.strip())
        return urls

    # 1) Direct post sitemap
    urls = _parse_sitemap_urls(POST_SITEMAP)
    if not urls:
        # 2) sitemap index -> find post sitemaps and pick the latest
        resp = session.get(SITEMAP_INDEX, timeout=20)
        resp.raise_for_status()
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            root = None
        if root is not None:
            ns_sitemap = "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap"
            entries = []
            for sm in root.findall(f".//{ns_sitemap}"):
                loc = sm.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if not loc:
                    continue
                if "post-sitemap" in loc:
                    entries.append(loc.strip())
            # Try latest by lexical order
            for loc in sorted(entries, reverse=True):
                urls = _parse_sitemap_urls(loc)
                if urls:
                    break

    articles: List[Article] = []
    for u in urls[:max_items * 3]:
        # Filter out obvious non-article pages
        if not (re.search(r"/20\d{2}/", u) or re.search(r"[?&]p=\d+", u)):
            continue
        title = u.rsplit('/', 2)[-2].replace('-', ' ')
        if not title:
            title = u
        articles.append(Article(title=title, url=u, published_at=None, summary=None, images=[]))
        if len(articles) >= max_items:
            break
    return articles
