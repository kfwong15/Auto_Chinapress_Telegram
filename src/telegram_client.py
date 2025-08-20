import logging
import os
from datetime import datetime

from .chinapress import fetch_latest
from .state_store import StateStore
from .telegram_client import TelegramClient

def build_message(title: str, url: str, published: str | None) -> str:
    parts = [f"<b>{title}</b>"]
    if published:
        parts.append(f"🕒 {published}")
    parts.append(url)
    return "\n".join(parts)

def parse_int_env(var_name: str, default: int) -> int:
    """Safely parse integer from environment variable, fallback to default if invalid or empty."""
    raw = os.getenv(var_name, str(default))
    try:
        return int(raw) if raw.strip() else default
    except ValueError:
        logging.warning("Invalid value for %s=%r, using default: %d", var_name, raw, default)
        return default

def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    max_items_total = parse_int_env("MAX_ITEMS_PER_RUN", 10)
    state = StateStore()
    state.load()
    tg = TelegramClient()

    articles = fetch_latest(max_items=max_items_total * 3)
    if not articles:
        logging.info("No articles fetched.")
        return 0

    sent_count = 0
    for article in articles:
        if state.has(article.url):
            continue
        text = build_message(article.title, article.url, article.published_at)
        tg.send_message(text)
        state.add(article.url)
        sent_count += 1
        if sent_count >= max_items_total:
            break

    if sent_count > 0:
        state.save()
        logging.info("Sent %d new items at %s", sent_count, datetime.utcnow().isoformat())
    else:
        logging.info("No new items to send.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
