import argparse
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from db import Store, utcnow_iso
from pricing import parse_price_observation


LOGGER = logging.getLogger("ppompu_backfill")


LIST_LINK_RE = re.compile(r"/zboard/(?:view|zboard)\.php\?id=([^&]+).*?\bno=(\d+)")
DATE_RE = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")


def parse_args():
    parser = argparse.ArgumentParser(description="One-time ppomppu backfill (6 months)")
    parser.add_argument("--db-path", default=os.getenv("DB_PATH", "/data/ppompu_bot.sqlite3"))
    parser.add_argument("--board-id", default=os.getenv("BACKFILL_BOARD_ID", "ppomppu"))
    parser.add_argument("--months", type=int, default=int(os.getenv("BACKFILL_MONTHS", "6")))
    parser.add_argument("--start-page", type=int, default=int(os.getenv("BACKFILL_START_PAGE", "1")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("BACKFILL_MAX_PAGES", "300")))
    parser.add_argument("--sleep-sec", type=float, default=float(os.getenv("BACKFILL_SLEEP_SEC", "0.5")))
    parser.add_argument("--base-url", default=os.getenv("PPOMPPU_BASE_URL", "https://www.ppomppu.co.kr"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logging():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def board_list_url(base_url: str, board_id: str, page: int) -> str:
    return f"{base_url}/zboard/zboard.php?id={board_id}&page={page}"


def post_item_id_from_link(link: str) -> Optional[str]:
    parsed = urlparse(link)
    qs = parse_qs(parsed.query)
    board_id = (qs.get("id") or [None])[0]
    no = (qs.get("no") or [None])[0]
    if board_id and no:
        return f"{board_id}:{no}"
    match = LIST_LINK_RE.search(link)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def iter_list_rows(html: str, base_url: str) -> Iterable[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen_links = set()
    # Prefer current desktop board list title anchors.
    anchors = list(soup.select("a.baseList-title"))
    # Fallback for older/different markup.
    if not anchors:
        anchors = soup.find_all("a")

    for a in anchors:
        href = (a.get("href") or "").strip()
        if not href or "view.php?id=" not in href:
            continue
        link = urljoin(base_url, href)
        if link in seen_links:
            continue
        seen_links.add(link)
        title = a.get_text(" ", strip=True)
        if not title:
            continue

        tr = a.find_parent("tr")
        row_text = tr.get_text(" ", strip=True) if tr else a.get_text(" ", strip=True)
        date_match = DATE_RE.search(row_text)
        date_iso = None
        if date_match:
            y, m, d = map(int, date_match.groups())
            date_iso = datetime(y, m, d, tzinfo=timezone.utc).date().isoformat()
        yield {"title": title, "link": link, "date_iso": date_iso}


def backfill():
    args = parse_args()
    setup_logging()
    store = Store(args.db_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        }
    )
    rss_url = f"{args.base_url}/rss.php?id={args.board_id}"
    inserted = 0
    seen = 0
    stopped_by_cutoff = False
    consecutive_no_rows = 0

    if args.start_page < 1:
        raise ValueError("--start-page must be >= 1")
    if args.max_pages < args.start_page:
        raise ValueError("--max-pages must be >= --start-page")

    for page in range(args.start_page, args.max_pages + 1):
        url = board_list_url(args.base_url, args.board_id, page)
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            # Ppomppu pages are commonly EUC-KR; force decode to stabilize parsing.
            resp.encoding = resp.encoding or "euc-kr"
        except Exception:
            LOGGER.exception("Failed to fetch page=%s url=%s", page, url)
            continue

        rows = list(iter_list_rows(resp.text, args.base_url))
        if not rows:
            consecutive_no_rows += 1
            LOGGER.warning("No rows parsed at page=%s (consecutive=%s)", page, consecutive_no_rows)
            if consecutive_no_rows >= 3:
                LOGGER.warning("Stopping backfill after %s consecutive parse misses", consecutive_no_rows)
                break
            continue
        consecutive_no_rows = 0

        LOGGER.info("page=%s parsed_rows=%s", page, len(rows))
        for row in rows:
            seen += 1
            if row["date_iso"]:
                row_dt = datetime.fromisoformat(row["date_iso"]).replace(tzinfo=timezone.utc)
                if row_dt < cutoff:
                    stopped_by_cutoff = True
                    break
            item_id = post_item_id_from_link(row["link"]) or row["link"]
            obs = parse_price_observation(
                item_id=item_id,
                title=row["title"],
                link=row["link"],
                board_rss_url=rss_url,
                source="backfill",
                published_at=row["date_iso"],
                crawled_at=utcnow_iso(),
            )
            if not obs:
                continue
            if args.dry_run:
                LOGGER.info("dry-run item=%s title=%s metric=%s", item_id, row["title"], obs.metric_text)
                continue
            store.upsert_deal(
                item_id=obs.item_id,
                board_rss_url=obs.board_rss_url,
                link=obs.link,
                title=obs.title,
                product_key=obs.product_key,
                total_price_krw=obs.total_price_krw,
                quantity_count=obs.quantity_count,
                metric_value_krw=obs.metric_value_krw,
                metric_basis=obs.metric_basis,
                source=obs.source,
                published_at=obs.published_at,
                crawled_at=obs.crawled_at,
            )
            inserted += 1

        if stopped_by_cutoff:
            LOGGER.info("Stopping at page=%s due to cutoff(%s)", page, cutoff.date().isoformat())
            break

        if args.sleep_sec > 0:
            import time

            time.sleep(args.sleep_sec)

    LOGGER.info(
        "Backfill finished board=%s seen_rows=%s deal_upserts=%s cutoff=%s",
        args.board_id,
        seen,
        inserted,
        cutoff.date().isoformat(),
    )


if __name__ == "__main__":
    backfill()
