import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import feedparser

from db import Store, normalize_keyword
from pricing import build_price_analysis, parse_price_observation

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
    from telegram.error import BadRequest
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except Exception:  # pragma: no cover
    Application = None  # type: ignore
    InlineKeyboardButton = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore
    KeyboardButton = None  # type: ignore
    ReplyKeyboardMarkup = None  # type: ignore
    Update = None  # type: ignore
    BadRequest = Exception  # type: ignore
    CallbackQueryHandler = None  # type: ignore
    CommandHandler = None  # type: ignore
    ContextTypes = None  # type: ignore
    MessageHandler = None  # type: ignore
    filters = None  # type: ignore


LOGGER = logging.getLogger("ppompu_bot")

CB_LIST_REFRESH = "list:refresh"
CB_LIST_ADD = "list:add"
CB_LIST_REMOVE = "list:remove"
CB_LIST_SHOW = "list:show"
CB_BOARD_PREFIX = "board:"

BTN_LIST = "\U0001F4CC \ud0a4\uc6cc\ub4dc \ubaa9\ub85d"
BTN_ADD = "\u2795 \ud0a4\uc6cc\ub4dc \ucd94\uac00"
BTN_REMOVE = "\U0001F5D1 \ud0a4\uc6cc\ub4dc \uc0ad\uc81c"
BTN_BOARD = "\U0001F9ED \uac8c\uc2dc\ud310 \uc120\ud0dd"
BTN_HELP = "\u2753 \ub3c4\uc6c0\ub9d0"
MENU_BUTTON_TEXTS = {BTN_LIST, BTN_ADD, BTN_REMOVE, BTN_BOARD, BTN_HELP}


@dataclass
class BoardOption:
    key: str
    label: str
    rss_url: str


@dataclass
class AppConfig:
    bot_token: str
    dry_run: bool
    dry_run_once: bool
    poll_interval_sec: int
    data_dir: str
    db_path: str
    board_options: Dict[str, BoardOption]
    default_board_key: str
    log_file: Optional[str]

    @property
    def default_board(self) -> BoardOption:
        return self.board_options[self.default_board_key]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_board_options() -> Tuple[Dict[str, BoardOption], str]:
    raw = os.getenv(
        "BOARD_OPTIONS",
        ",".join(
            [
                "ppomppu|\ubf50\ubfd0\uac8c\uc2dc\ud310|https://www.ppomppu.co.kr/rss.php?id=ppomppu",
                "phone|\ud734\ub300\ud3f0\ud3ec\ub7fc|https://www.ppomppu.co.kr/rss.php?id=phone",
                "freeboard|\uc790\uc720\uac8c\uc2dc\ud310|https://www.ppomppu.co.kr/rss.php?id=freeboard",
            ]
        ),
    )
    options: Dict[str, BoardOption] = {}
    for chunk in [x.strip() for x in raw.split(",") if x.strip()]:
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) == 3:
            key, label, url = parts
        elif len(parts) == 2:
            key, url = parts
            label = key
        else:
            continue
        options[key] = BoardOption(key=key, label=label, rss_url=url)
    if not options:
        raise ValueError("No board options configured")
    default_key = os.getenv("DEFAULT_BOARD_KEY", next(iter(options.keys())))
    if default_key not in options:
        default_key = next(iter(options.keys()))
    return options, default_key


def load_config() -> AppConfig:
    data_dir = os.getenv("DATA_DIR", "/data")
    db_path = os.getenv("DB_PATH", os.path.join(data_dir, "ppompu_bot.sqlite3"))
    board_options, default_board_key = parse_board_options()
    return AppConfig(
        bot_token=os.getenv("BOT_TOKEN", ""),
        dry_run=env_bool("DRY_RUN", False),
        dry_run_once=env_bool("DRY_RUN_ONCE", False),
        poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "300")),
        data_dir=data_dir,
        db_path=db_path,
        board_options=board_options,
        default_board_key=default_board_key,
        log_file=os.getenv("LOG_FILE"),
    )


def setup_logging(log_file: Optional[str]) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        parent = os.path.dirname(log_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def item_id_from_entry(entry) -> str:
    for key in ("id", "guid", "link", "title"):
        value = getattr(entry, key, None) or entry.get(key)
        if value:
            return str(value)
    return ""


def entry_title(entry) -> str:
    return str(getattr(entry, "title", None) or entry.get("title") or "(\uc81c\ubaa9 \uc5c6\uc74c)")


def entry_link(entry) -> str:
    return str(getattr(entry, "link", None) or entry.get("link") or "")


def entry_published_at(entry) -> Optional[str]:
    for key in ("published", "updated"):
        value = getattr(entry, key, None) or entry.get(key)
        if value:
            return str(value)
    return None


def entry_text_for_match(entry) -> str:
    return " ".join(
        [
            str(getattr(entry, "title", None) or entry.get("title") or ""),
            str(getattr(entry, "summary", None) or entry.get("summary") or ""),
        ]
    ).casefold()


def match_keyword(entry, keywords: List[str]) -> Optional[str]:
    haystack = entry_text_for_match(entry)
    for keyword in keywords:
        if keyword and keyword in haystack:
            return keyword
    return None


def format_scan_time(raw: Optional[str]) -> str:
    return "\uc5c6\uc74c" if not raw else str(raw).replace("+00:00", "Z")


def list_keyboard():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("\u2795 \ucd94\uac00", callback_data=CB_LIST_ADD),
            InlineKeyboardButton("\U0001F5D1 \uc0ad\uc81c", callback_data=CB_LIST_REMOVE),
            InlineKeyboardButton("\U0001F504 \uc0c8\ub85c\uace0\uce68", callback_data=CB_LIST_REFRESH),
        ]]
    )


def alert_keyboard(url: str):
    row = [InlineKeyboardButton("\ud0a4\uc6cc\ub4dc \ubaa9\ub85d", callback_data=CB_LIST_SHOW)]
    if url:
        row.insert(0, InlineKeyboardButton("\uc5f4\uae30", url=url))
    return InlineKeyboardMarkup([row])


def board_keyboard(config: AppConfig):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.label, callback_data=f"{CB_BOARD_PREFIX}{b.key}")] for b in config.board_options.values()]
    )


def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_LIST), KeyboardButton(BTN_ADD)],
            [KeyboardButton(BTN_REMOVE), KeyboardButton(BTN_BOARD)],
            [KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def render_list_text(keywords: List[str]) -> str:
    if not keywords:
        return "\ub4f1\ub85d\ub41c \ud0a4\uc6cc\ub4dc\uac00 \uc5c6\uc5b4\uc694.\n\u2795 \ucd94\uac00 \ubc84\ud2bc\uc73c\ub85c \ub4f1\ub85d\ud558\uc138\uc694."
    lines = [f"\U0001F4CC \ub0b4 \ud0a4\uc6cc\ub4dc(\ucd1d {len(keywords)}\uac1c)"]
    for i, k in enumerate(keywords, start=1):
        lines.append(f"{i}) {k}")
    return "\n".join(lines)


def resolve_chat_id(update: "Update") -> Optional[str]:
    return str(update.effective_chat.id) if update.effective_chat and update.effective_chat.id is not None else None


async def send_or_edit_message(query, text: str, reply_markup=None):
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return
        raise


class BotRuntime:
    def __init__(self, config: AppConfig, store: Store):
        self.config = config
        self.store = store

    def current_board_for_chat(self, chat_id: str) -> BoardOption:
        rss_url = self.store.get_board(chat_id) or self.config.default_board.rss_url
        for board in self.config.board_options.values():
            if board.rss_url == rss_url:
                return board
        return BoardOption(key="custom", label="Custom", rss_url=rss_url)

    async def _reply(self, message, text: str, reply_markup=None) -> None:
        await message.reply_text(text, reply_markup=reply_markup or main_menu_keyboard())

    def _split_csv_tokens(self, raw_text: str) -> List[str]:
        text = (raw_text or "").strip()
        if not text:
            return []
        return [p.strip() for p in text.split(",")] if "," in text else [text]

    async def _handle_menu_button_text(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE", text: str) -> bool:
        message = update.effective_message
        chat_id = resolve_chat_id(update)
        if not message or not chat_id:
            return False
        if text == BTN_LIST:
            self.store.set_ui_state(chat_id, "IDLE")
            await self.cmd_list(update, context)
            return True
        if text == BTN_ADD:
            self.store.set_ui_state(chat_id, "ADD_WAIT")
            await self._reply(message, "\ucd94\uac00\ud560 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return True
        if text == BTN_REMOVE:
            self.store.set_ui_state(chat_id, "REMOVE_WAIT")
            await self._reply(message, "\uc0ad\uc81c\ud560 \ubc88\ud638 \ub610\ub294 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return True
        if text == BTN_BOARD:
            self.store.set_ui_state(chat_id, "IDLE")
            await self.cmd_setboard(update, context)
            return True
        if text == BTN_HELP:
            self.store.set_ui_state(chat_id, "IDLE")
            await self.cmd_help(update, context)
            return True
        return False

    async def cmd_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        count = self.store.keyword_count(chat_id)
        board = self.current_board_for_chat(chat_id)
        text = (
            "\ubf50\ubfd0 \ud0a4\uc6cc\ub4dc \uc54c\ub9bc \ubd07\uc785\ub2c8\ub2e4.\n"
            f"\ud0a4\uc6cc\ub4dc: {count}\uac1c | \uac8c\uc2dc\ud310: {board.label}\n"
            f"\ub9c8\uc9c0\ub9c9 \uc2a4\uce94: {format_scan_time(self.store.get_meta('last_scan_at'))}\n"
            "\uc544\ub798 \ubc84\ud2bc\uc73c\ub85c \uad00\ub9ac\ud558\uc138\uc694."
        )
        await self._reply(update.effective_message, text)

    async def cmd_help(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        text = (
            "\uba85\ub839\uc5b4 \ub3c4\uc6c0\ub9d0\n"
            "/list, /add, /remove, /setboard\n"
            "/add \ud587\ubc18, \uc624\ub808\uc624 (\uc27c\ud45c \ub2e4\uc911 \ucd94\uac00)\n"
            "/remove 1,3,\ud587\ubc18 (\uc27c\ud45c \ub2e4\uc911 \uc0ad\uc81c)\n"
            "\ud558\ub2e8 \uba54\ub274 \ubc84\ud2bc \uc0ac\uc6a9 \uac00\ub2a5"
        )
        await self._reply(update.effective_message, text)

    async def cmd_add(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        if not context.args:
            self.store.set_ui_state(chat_id, "ADD_WAIT")
            await self._reply(update.effective_message, "\ucd94\uac00\ud560 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return
        await self._handle_add_keyword(update.effective_message, chat_id, " ".join(context.args))

    async def _handle_add_keyword(self, message, chat_id: str, raw_keyword: str) -> None:
        tokens = [t for t in self._split_csv_tokens(raw_keyword) if t]
        if not tokens:
            await self._reply(message, "\ube48 \ud0a4\uc6cc\ub4dc\ub294 \ucd94\uac00\ud560 \uc218 \uc5c6\uc5b4\uc694.")
            return
        if any(t in MENU_BUTTON_TEXTS for t in tokens):
            self.store.set_ui_state(chat_id, "IDLE")
            await self._reply(message, "\uba54\ub274 \ubc84\ud2bc \ubb38\uad6c\ub294 \ud0a4\uc6cc\ub4dc\ub85c \ub4f1\ub85d\ub418\uc9c0 \uc54a\uc544\uc694.")
            return
        added, dup = [], []
        count = self.store.keyword_count(chat_id)
        for token in tokens:
            try:
                ok, keyword, count = self.store.add_keyword(chat_id, token)
            except ValueError:
                continue
            (added if ok else dup).append(keyword)
        self.store.set_ui_state(chat_id, "IDLE")
        if len(tokens) == 1:
            if added:
                await self._reply(message, f"\u2705 \ucd94\uac00\ub428: {added[0]} (\ucd1d {count}\uac1c)")
            elif dup:
                await self._reply(message, f"\u26A0 \uc774\ubbf8 \ub4f1\ub85d\ub428: {dup[0]}")
            else:
                await self._reply(message, "\ube48 \ud0a4\uc6cc\ub4dc\ub294 \ucd94\uac00\ud560 \uc218 \uc5c6\uc5b4\uc694.")
            return
        lines = [f"\u2705 \ucd94\uac00 {len(added)}\uac1c / \uc911\ubcf5 {len(dup)}\uac1c (\ucd1d {count}\uac1c)"]
        if added:
            lines.append("\ucd94\uac00: " + ", ".join(added[:8]))
        if dup:
            lines.append("\uc911\ubcf5: " + ", ".join(dup[:8]))
        await self._reply(message, "\n".join(lines))

    async def cmd_remove(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        if not context.args:
            self.store.set_ui_state(chat_id, "REMOVE_WAIT")
            await self._reply(update.effective_message, "\uc0ad\uc81c\ud560 \ubc88\ud638 \ub610\ub294 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return
        await self._handle_remove_keyword(update.effective_message, chat_id, " ".join(context.args))

    async def _handle_remove_keyword(self, message, chat_id: str, target: str) -> None:
        tokens = [t for t in self._split_csv_tokens(target) if t]
        if not tokens:
            await self._reply(message, "\uc0ad\uc81c\ud560 \ubc88\ud638 \ub610\ub294 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694.")
            return
        if len(tokens) == 1:
            ok, removed, count = self.store.remove_keyword(chat_id, tokens[0])
            self.store.set_ui_state(chat_id, "IDLE")
            await self._reply(message, f"\u2705 \uc0ad\uc81c\ub428: {removed} (\ucd1d {count}\uac1c)" if ok and removed else "\ucc3e\uc744 \uc218 \uc5c6\ub294 \ud0a4\uc6cc\ub4dc/\ubc88\ud638\uc608\uc694.")
            return
        snapshot = [k.keyword for k in self.store.list_keywords(chat_id)]
        resolved, seen = [], set()
        for t in tokens:
            key = None
            if t.isdigit():
                idx = int(t)
                if 1 <= idx <= len(snapshot):
                    key = snapshot[idx - 1]
            else:
                norm = normalize_keyword(t)
                if norm:
                    key = norm
            if key and key not in seen:
                seen.add(key)
                resolved.append(key)
        removed_items, miss = [], max(0, len(tokens) - len(resolved))
        count = self.store.keyword_count(chat_id)
        for key in resolved:
            ok, removed, count = self.store.remove_keyword(chat_id, key)
            if ok and removed:
                removed_items.append(removed)
            else:
                miss += 1
        self.store.set_ui_state(chat_id, "IDLE")
        lines = [f"\u2705 \uc0ad\uc81c {len(removed_items)}\uac1c / \uc2e4\ud328 {miss}\uac1c (\ucd1d {count}\uac1c)"]
        if removed_items:
            lines.append("\uc0ad\uc81c: " + ", ".join(removed_items[:8]))
        await self._reply(message, "\n".join(lines))

    async def cmd_list(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        await self._reply(update.effective_message, render_list_text([k.keyword for k in self.store.list_keywords(chat_id)]), reply_markup=list_keyboard())

    async def cmd_setboard(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        current = self.current_board_for_chat(chat_id)
        await self._reply(update.effective_message, f"\ud604\uc7ac \uac8c\uc2dc\ud310: {current.label}\n\ubcc0\uacbd\ud560 \uac8c\uc2dc\ud310\uc744 \uc120\ud0dd\ud558\uc138\uc694.", reply_markup=board_keyboard(self.config))

    async def on_text_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        message = update.effective_message
        chat_id = resolve_chat_id(update)
        if not message or not chat_id or not message.text:
            return
        if await self._handle_menu_button_text(update, context, message.text):
            return
        mode, _payload = self.store.get_ui_state(chat_id)
        if mode == "ADD_WAIT":
            await self._handle_add_keyword(message, chat_id, message.text)
            return
        if mode == "REMOVE_WAIT":
            await self._handle_remove_keyword(message, chat_id, message.text)
            return
        await self._reply(message, "\uc544\ub798 \ubc84\ud2bc\uc73c\ub85c \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.")

    async def on_callback(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        chat_id = resolve_chat_id(update)
        if not chat_id:
            return
        data = query.data or ""
        if data in {CB_LIST_REFRESH, CB_LIST_SHOW}:
            await send_or_edit_message(query, render_list_text([k.keyword for k in self.store.list_keywords(chat_id)]), reply_markup=list_keyboard())
            return
        if data == CB_LIST_ADD:
            self.store.set_ui_state(chat_id, "ADD_WAIT")
            await self._reply(query.message, "\ucd94\uac00\ud560 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return
        if data == CB_LIST_REMOVE:
            self.store.set_ui_state(chat_id, "REMOVE_WAIT")
            await self._reply(query.message, "\uc0ad\uc81c\ud560 \ubc88\ud638 \ub610\ub294 \ud0a4\uc6cc\ub4dc\ub97c \uc785\ub825\ud558\uc138\uc694. (,\ub85c \uc5ec\ub7ec \uac1c \uac00\ub2a5)")
            return
        if data.startswith(CB_BOARD_PREFIX):
            board = self.config.board_options.get(data[len(CB_BOARD_PREFIX):])
            if not board:
                await self._reply(query.message, "\uc54c \uc218 \uc5c6\ub294 \uac8c\uc2dc\ud310 \uc120\ud0dd\uc785\ub2c8\ub2e4.")
                return
            self.store.set_board(chat_id, board.rss_url)
            await send_or_edit_message(query, f"\u2705 \uac8c\uc2dc\ud310 \ubcc0\uacbd\ub428: {board.label}", reply_markup=board_keyboard(self.config))
            await self._reply(query.message, f"\ud604\uc7ac \uac8c\uc2dc\ud310: {board.label}")

    async def on_error(self, update: object, context: "ContextTypes.DEFAULT_TYPE") -> None:
        LOGGER.exception("Telegram handler error", exc_info=context.error)

    async def run_scan_once(self, application: Optional["Application"] = None) -> None:
        grouped = self.store.get_subscribers_by_board(self.config.default_board.rss_url)
        if not grouped:
            self.store.set_meta("last_scan_at", utcnow_iso())
            return
        for rss_url, chat_ids in grouped.items():
            try:
                feed = feedparser.parse(rss_url)
            except Exception:
                LOGGER.exception("Feed parse failed: %s", rss_url)
                continue
            entries = list(getattr(feed, "entries", []) or [])
            if not entries:
                continue
            kw_map = self.store.get_keywords_for_chats(chat_ids)
            for entry in entries:
                item_id = item_id_from_entry(entry)
                if not item_id:
                    continue
                title = entry_title(entry)
                link = entry_link(entry)
                obs = parse_price_observation(item_id=item_id, title=title, link=link, board_rss_url=rss_url, source="rss", published_at=entry_published_at(entry))
                analysis_line: Optional[str] = None
                if obs:
                    self.store.upsert_deal(
                        item_id=obs.item_id, board_rss_url=obs.board_rss_url, link=obs.link, title=obs.title,
                        product_key=obs.product_key, total_price_krw=obs.total_price_krw, quantity_count=obs.quantity_count,
                        metric_value_krw=obs.metric_value_krw, metric_basis=obs.metric_basis, source=obs.source,
                        published_at=obs.published_at, crawled_at=obs.crawled_at,
                    )
                    prev_vals = self.store.get_previous_metric_values(product_key=obs.product_key, metric_basis=obs.metric_basis, current_item_id=obs.item_id, limit=30)
                    analysis = build_price_analysis(obs.metric_value_krw, obs.metric_basis, prev_vals)
                    if analysis:
                        analysis_line = analysis.to_alert_line()
                for chat_id in chat_ids:
                    matched = match_keyword(entry, kw_map.get(chat_id, []))
                    if not matched or not self.store.mark_sent_if_new(chat_id, item_id):
                        continue
                    try:
                        await self._deliver_alert(application, chat_id, matched, title, link, analysis_line)
                    except Exception:
                        self.store.delete_sent(chat_id, item_id)
                        LOGGER.exception("Alert send failed chat_id=%s item_id=%s", chat_id, item_id)
        self.store.set_meta("last_scan_at", utcnow_iso())

    async def _deliver_alert(self, application: Optional["Application"], chat_id: str, matched_keyword: str, title: str, link: str, analysis_line: Optional[str] = None) -> None:
        lines = [f"\U0001F6A8 [\ubf50\ubfd0] \ud0a4\uc6cc\ub4dc \uac10\uc9c0", f"\U0001F3AF \ud0a4\uc6cc\ub4dc: {matched_keyword}", f"\U0001F4CC \uc81c\ubaa9: {title}"]
        if analysis_line:
            lines.append(analysis_line)
        lines.append(f"\U0001F517 {link}")
        text = "\n".join(lines)
        if self.config.dry_run or application is None:
            print(f"[DRY-RUN][{chat_id}] {text}")
            return
        await application.bot.send_message(chat_id=chat_id, text=text, reply_markup=alert_keyboard(link))


async def scheduled_scan(context: "ContextTypes.DEFAULT_TYPE") -> None:
    await context.application.bot_data["runtime"].run_scan_once(application=context.application)


def build_application(config: AppConfig, runtime: BotRuntime) -> "Application":
    if Application is None:
        raise RuntimeError("python-telegram-bot not installed")
    if not config.bot_token:
        raise RuntimeError("BOT_TOKEN required unless DRY_RUN=1")
    app = Application.builder().token(config.bot_token).build()
    app.bot_data["runtime"] = runtime
    app.add_handler(CommandHandler("start", runtime.cmd_start))
    app.add_handler(CommandHandler("help", runtime.cmd_help))
    app.add_handler(CommandHandler("list", runtime.cmd_list))
    app.add_handler(CommandHandler("add", runtime.cmd_add))
    app.add_handler(CommandHandler("remove", runtime.cmd_remove))
    app.add_handler(CommandHandler("setboard", runtime.cmd_setboard))
    app.add_handler(CallbackQueryHandler(runtime.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, runtime.on_text_message))
    app.add_error_handler(runtime.on_error)
    if app.job_queue is None:
        raise RuntimeError("JobQueue unavailable")
    app.job_queue.run_repeating(scheduled_scan, interval=config.poll_interval_sec, first=5)
    return app


async def run_dry_mode(runtime: BotRuntime, config: AppConfig) -> None:
    while True:
        await runtime.run_scan_once(application=None)
        if config.dry_run_once:
            break
        await asyncio.sleep(config.poll_interval_sec)


def main() -> None:
    config = load_config()
    os.makedirs(config.data_dir, exist_ok=True)
    setup_logging(config.log_file)
    store = Store(config.db_path)
    runtime = BotRuntime(config, store)
    if config.dry_run:
        asyncio.run(run_dry_mode(runtime, config))
        return
    build_application(config, runtime).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
