import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_keyword(value: str) -> str:
    if value is None:
        return ""
    normalized = " ".join(value.strip().split())
    return normalized.casefold()


@dataclass
class KeywordRecord:
    keyword: str
    created_at: str


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS keywords (
                    chat_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, keyword)
                );

                CREATE TABLE IF NOT EXISTS sent (
                    chat_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS ui_state (
                    chat_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    payload TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS boards (
                    chat_id TEXT PRIMARY KEY,
                    rss_url TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS deals (
                    item_id TEXT PRIMARY KEY,
                    board_rss_url TEXT NOT NULL,
                    link TEXT,
                    title TEXT NOT NULL,
                    product_key TEXT,
                    total_price_krw INTEGER,
                    quantity_count INTEGER,
                    metric_value_krw REAL,
                    metric_basis TEXT,
                    source TEXT NOT NULL,
                    published_at TEXT,
                    crawled_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_deals_product_metric
                    ON deals(product_key, metric_basis, crawled_at);
                """
            )

    def add_keyword(self, chat_id: str, raw_keyword: str) -> Tuple[bool, str, int]:
        keyword = normalize_keyword(raw_keyword)
        if not keyword:
            raise ValueError("empty keyword")
        with self.connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO keywords(chat_id, keyword, created_at) VALUES (?, ?, ?)",
                    (chat_id, keyword, utcnow_iso()),
                )
                added = True
            except sqlite3.IntegrityError:
                added = False
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM keywords WHERE chat_id = ?", (chat_id,)
            ).fetchone()["c"]
        return added, keyword, int(count)

    def list_keywords(self, chat_id: str) -> List[KeywordRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT keyword, created_at FROM keywords WHERE chat_id = ? ORDER BY keyword ASC",
                (chat_id,),
            ).fetchall()
        return [KeywordRecord(keyword=row["keyword"], created_at=row["created_at"]) for row in rows]

    def keyword_count(self, chat_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM keywords WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return int(row["c"])

    def remove_keyword(self, chat_id: str, keyword_or_index: str) -> Tuple[bool, Optional[str], int]:
        removed_keyword: Optional[str] = None
        value = (keyword_or_index or "").strip()
        with self.connect() as conn:
            if value.isdigit():
                idx = int(value)
                rows = conn.execute(
                    "SELECT keyword FROM keywords WHERE chat_id = ? ORDER BY keyword ASC",
                    (chat_id,),
                ).fetchall()
                if 1 <= idx <= len(rows):
                    removed_keyword = rows[idx - 1]["keyword"]
            else:
                normalized = normalize_keyword(value)
                if normalized:
                    row = conn.execute(
                        "SELECT keyword FROM keywords WHERE chat_id = ? AND keyword = ?",
                        (chat_id, normalized),
                    ).fetchone()
                    if row:
                        removed_keyword = row["keyword"]

            if removed_keyword:
                conn.execute(
                    "DELETE FROM keywords WHERE chat_id = ? AND keyword = ?",
                    (chat_id, removed_keyword),
                )
                success = True
            else:
                success = False

            count = conn.execute(
                "SELECT COUNT(*) AS c FROM keywords WHERE chat_id = ?", (chat_id,)
            ).fetchone()["c"]

        return success, removed_keyword, int(count)

    def get_ui_state(self, chat_id: str) -> Tuple[str, Optional[dict]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT mode, payload FROM ui_state WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        if not row:
            return "IDLE", None
        payload = json.loads(row["payload"]) if row["payload"] else None
        return row["mode"], payload

    def set_ui_state(self, chat_id: str, mode: str, payload: Optional[dict] = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ui_state(chat_id, mode, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    mode=excluded.mode,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (chat_id, mode, json.dumps(payload) if payload is not None else None, utcnow_iso()),
            )

    def get_board(self, chat_id: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT rss_url FROM boards WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row["rss_url"] if row else None

    def set_board(self, chat_id: str, rss_url: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO boards(chat_id, rss_url, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    rss_url=excluded.rss_url,
                    updated_at=excluded.updated_at
                """,
                (chat_id, rss_url, utcnow_iso()),
            )

    def get_subscribers_by_board(self, default_rss_url: str) -> Dict[str, List[str]]:
        with self.connect() as conn:
            keyword_chats = [row["chat_id"] for row in conn.execute("SELECT DISTINCT chat_id FROM keywords")]
            explicit = {
                row["chat_id"]: row["rss_url"]
                for row in conn.execute("SELECT chat_id, rss_url FROM boards")
            }
        grouped: Dict[str, List[str]] = {}
        for chat_id in keyword_chats:
            rss_url = explicit.get(chat_id, default_rss_url)
            grouped.setdefault(rss_url, []).append(chat_id)
        return grouped

    def mark_sent_if_new(self, chat_id: str, item_id: str) -> bool:
        with self.connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO sent(chat_id, item_id, sent_at) VALUES (?, ?, ?)",
                    (chat_id, item_id, utcnow_iso()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_sent(self, chat_id: str, item_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sent WHERE chat_id = ? AND item_id = ?", (chat_id, item_id))

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO meta(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, utcnow_iso()),
            )

    def get_meta(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def get_keywords_for_chats(self, chat_ids: Iterable[str]) -> Dict[str, List[str]]:
        chat_ids = list(chat_ids)
        if not chat_ids:
            return {}
        placeholders = ",".join("?" for _ in chat_ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT chat_id, keyword FROM keywords WHERE chat_id IN ({placeholders}) ORDER BY keyword ASC",
                tuple(chat_ids),
            ).fetchall()
        result: Dict[str, List[str]] = {chat_id: [] for chat_id in chat_ids}
        for row in rows:
            result.setdefault(row["chat_id"], []).append(row["keyword"])
        return result

    def upsert_deal(
        self,
        *,
        item_id: str,
        board_rss_url: str,
        link: str,
        title: str,
        product_key: Optional[str],
        total_price_krw: Optional[int],
        quantity_count: Optional[int],
        metric_value_krw: Optional[float],
        metric_basis: Optional[str],
        source: str,
        published_at: Optional[str],
        crawled_at: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO deals(
                    item_id, board_rss_url, link, title, product_key,
                    total_price_krw, quantity_count, metric_value_krw, metric_basis,
                    source, published_at, crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    board_rss_url=excluded.board_rss_url,
                    link=excluded.link,
                    title=excluded.title,
                    product_key=excluded.product_key,
                    total_price_krw=excluded.total_price_krw,
                    quantity_count=excluded.quantity_count,
                    metric_value_krw=excluded.metric_value_krw,
                    metric_basis=excluded.metric_basis,
                    source=excluded.source,
                    published_at=excluded.published_at,
                    crawled_at=excluded.crawled_at
                """,
                (
                    item_id,
                    board_rss_url,
                    link,
                    title,
                    product_key,
                    total_price_krw,
                    quantity_count,
                    metric_value_krw,
                    metric_basis,
                    source,
                    published_at,
                    crawled_at or utcnow_iso(),
                ),
            )

    def get_previous_metric_values(
        self,
        *,
        product_key: Optional[str],
        metric_basis: Optional[str],
        current_item_id: Optional[str] = None,
        limit: int = 30,
    ) -> List[float]:
        if not product_key or not metric_basis:
            return []
        params: List[object] = [product_key, metric_basis]
        sql = """
            SELECT metric_value_krw
            FROM deals
            WHERE product_key = ?
              AND metric_basis = ?
              AND metric_value_krw IS NOT NULL
        """
        if current_item_id:
            sql += " AND item_id <> ?"
            params.append(current_item_id)
        sql += " ORDER BY COALESCE(published_at, crawled_at) DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        values = []
        for row in reversed(rows):
            try:
                values.append(float(row["metric_value_krw"]))
            except (TypeError, ValueError):
                continue
        return values

    def search_deals(self, query: str, limit: int = 200) -> List[sqlite3.Row]:
        raw = (query or "").strip()
        if not raw:
            return []
        norm = normalize_keyword(raw)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    item_id, board_rss_url, link, title, product_key,
                    total_price_krw, quantity_count, metric_value_krw, metric_basis,
                    source, published_at, crawled_at
                FROM deals
                WHERE
                    product_key LIKE ?
                    OR lower(title) LIKE lower(?)
                ORDER BY COALESCE(published_at, crawled_at) DESC, item_id DESC
                LIMIT ?
                """,
                (f"%{norm}%", f"%{raw}%", limit),
            ).fetchall()
        return rows
