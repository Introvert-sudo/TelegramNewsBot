import html as std_html
import asyncio
import datetime
import logging
from typing import Optional

from aiogram import Router, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.news_parser import get_latest
from app.data import db
from app.data.db import (
    init_db,
    upsert_user,
    set_subscription_active,
    is_subscribed,
    update_last_sent,
    get_last_sent,
    list_subscribed_users,
)

logger = logging.getLogger(__name__)
router = Router()

# === Configuration constants ===
FETCH_INTERVAL_SECONDS = 5  # how often to refresh the feed (seconds)
TECHCRUNCH_FEED = "https://techcrunch.com/feed/"  # RSS feed URL


# === Caching layer ===
class LatestItemCache:
    """
    Thread-safe time-based cache for the latest news item.

    Encapsulates the logic of avoiding frequent blocking fetches by reusing
    a cached value for a short interval.
    """

    def __init__(self, fetch_func, interval_seconds: float):
        self._fetch_func = fetch_func
        self._interval = interval_seconds
        self._cached: Optional[dict] = None
        self._cached_at: Optional[datetime.datetime] = None
        self._lock = asyncio.Lock()

    async def get(self) -> Optional[dict]:
        """
        Return cached item if fresh; otherwise fetch a new one in a thread
        to avoid blocking the event loop.
        """
        async with self._lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            if self._cached and self._cached_at:
                age = (now - self._cached_at).total_seconds()
                if age < self._interval:
                    return self._cached

            try:
                item = await asyncio.to_thread(self._fetch_func)
                if item:
                    self._cached = item
                    self._cached_at = now
                    return item
            except Exception as exc:
                logger.exception("Failed to fetch fresh latest item: %s", exc)
                # fallback to previous cached value if available
                return self._cached

            return None


# Singleton cache instance
_latest_cache = LatestItemCache(lambda: get_latest(TECHCRUNCH_FEED), FETCH_INTERVAL_SECONDS)


async def get_latest_item() -> Optional[dict]:
    """Convenience wrapper to get the latest news item with caching."""
    return await _latest_cache.get()


# === Presentation helper ===
def build_html_message(item: Optional[dict]) -> str:
    """
    Build an HTML-formatted message from a news item dict.
    Falls back gracefully if fields are missing or malformed.
    """
    if not item:
        return "No available articles."

    title = std_html.escape(item.get("title", "No title"))
    link = std_html.escape(item.get("link", "")) if item.get("link") else ""
    author = std_html.escape(item.get("author") or "Unknown")
    published_dt = item.get("published")
    published_str = ""
    if published_dt:
        try:
            published_str = published_dt.astimezone().strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            published_str = str(published_dt)
    summary_raw = (item.get("summary") or "").strip()
    summary = std_html.escape(summary_raw)
    if len(summary_raw) > 500:
        summary = std_html.escape(summary_raw[:497] + "...")

    parts = [
        f"<b>{title}</b>",
        f"<a href=\"{link}\">Read on site</a>" if link else "",
        f"<i>{author}</i>",
        published_str,
        summary,
    ]
    return "\n".join(p for p in parts if p)


# === Inline keyboard helpers ===
def build_settings_keyboard(is_active: bool):
    """
    Build the inline keyboard for toggling subscription state.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if is_active:
        button = InlineKeyboardButton(text="Disable", callback_data="stop_news")
    else:
        button = InlineKeyboardButton(text="Enable", callback_data="start_news")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


# === State for managing the initial prompt message ===
_last_intro_message: dict[int, tuple[int, int]] = {}  # user_id -> (chat_id, message_id)


# === Command handlers ===
@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Handle /start: create user only if missing; do not reset existing subscription.
    Sends initial prompt with current subscription status.
    """
    try:
        await init_db()
        user_id = message.from_user.id

        existing = await db.get_user(user_id)
        if not existing:
            await upsert_user(user_id)
            await set_subscription_active(user_id, False)

        subscribed = await is_subscribed(user_id)
        reply = await message.answer(
            "Do you want to receive the latest news? Change your preference below. You can always use /settings later.",
            reply_markup=build_settings_keyboard(subscribed),
        )
        # remember this prompt so /settings can remove it to avoid duplication
        _last_intro_message[user_id] = (reply.chat.id, reply.message_id)
    except Exception:
        logger.exception("Error in /start handler")
        await message.answer("An error occurred during setup. Please try again later.")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """
    Handle /settings: show current subscription status and allow toggle.
    Also deletes the initial prompt if it exists to prevent duplicate UI.
    """
    try:
        user_id = message.from_user.id

        # remove prior intro message to avoid clutter
        prev = _last_intro_message.pop(user_id, None)
        if prev:
            chat_id, msg_id = prev
            try:
                await message.bot.delete_message(chat_id, msg_id)
            except Exception:
                # safe to ignore deletion failure
                pass

        subscribed = await is_subscribed(user_id)
        status_text = "enabled" if subscribed else "disabled"
        keyboard = build_settings_keyboard(subscribed)
        await message.answer(
            f"News subscription is currently *{status_text}*. You can change it below or use this command again later.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Error in /settings handler")
        await message.answer("Failed to retrieve settings. Please try again later.")


@router.callback_query(lambda c: c.data == "start_news")
async def callback_start_news(callback: CallbackQuery):
    """
    Enable subscription, edit the invoking message to reflect status change,
    and immediately send the latest news item.
    """
    user_id = callback.from_user.id
    try:
        await upsert_user(user_id)  # safe no-op if exists
        await set_subscription_active(user_id, True)
        await callback.answer()

        # edit the original message to show confirmation and remove buttons
        try:
            await callback.message.edit_text(
                "Subscription enabled. To change your preferences, use /settings."
            )
        except Exception:
            pass  # might fail if message is too old or already edited

        item = await get_latest_item()
        if not item:
            await callback.message.reply("Failed to retrieve the latest news.")
            return

        text = build_html_message(item)
        await callback.message.reply(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )

        published_dt = item.get("published")
        if published_dt:
            await update_last_sent(user_id, published_dt)
    except Exception:
        logger.exception("Error in callback_start_news for user_id=%s", user_id)
        await callback.message.reply("Something went wrong while activating your subscription.")


@router.callback_query(lambda c: c.data == "stop_news")
async def callback_stop_news(callback: CallbackQuery):
    """
    Disable subscription and edit the invoking message to reflect that.
    """
    user_id = callback.from_user.id
    try:
        await set_subscription_active(user_id, False)
        await callback.answer("Subscription stopped.")

        try:
            await callback.message.edit_text(
                "Subscription disabled. To change your preferences, use /settings."
            )
        except Exception:
            pass

        await callback.message.reply("News notifications have been disabled.")
    except Exception:
        logger.exception("Error in callback_stop_news for user_id=%s", user_id)
        await callback.message.reply("Failed to stop subscription. Please try again later.")


@router.message(Command("latest"))
async def cmd_latest(message: Message):
    """
    On-demand retrieval of the most recent (cached) article.
    """
    try:
        item = await get_latest_item()
        if not item:
            await message.reply("Could not find any articles in this feed.")
            return

        text = build_html_message(item)
        await message.reply(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    except Exception:
        logger.exception("Error in /latest handler")
        await message.reply("Error while fetching the latest news.")


# === Background polling ===
async def background_polling_loop(bot: Bot):
    """
    Periodically fetch the latest item and dispatch to subscribed users if it's new.
    Uses exponential backoff on failure to avoid tight crash loops.
    """
    backoff_delay = 1.0
    while True:
        try:
            await asyncio.sleep(FETCH_INTERVAL_SECONDS)
            latest = await get_latest_item()
            if not latest:
                continue

            subscribers = await list_subscribed_users()
            if not subscribers:
                continue

            published_dt = latest.get("published")
            if not published_dt:
                continue

            for user_id in subscribers:
                try:
                    if not await is_subscribed(user_id):
                        continue

                    last_sent = await get_last_sent(user_id)
                    if (last_sent is None) or (published_dt > last_sent):
                        text = build_html_message(latest)
                        await bot.send_message(
                            user_id,
                            text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=False,
                        )
                        await update_last_sent(user_id, published_dt)
                except Exception:
                    logger.exception("Failed to send news to user %s", user_id)
                    # continue with others

            backoff_delay = 1.0  # reset after success
        except Exception:
            logger.exception("Background loop crashed; retrying in %.1f seconds", backoff_delay)
            await asyncio.sleep(backoff_delay)
            backoff_delay = min(backoff_delay * 2, 60)


# keep reference so we don't spawn duplicates
_background_task: Optional[asyncio.Task] = None


def setup_background_task(bot: Bot):
    """
    Start the polling background task if it's not already running.
    """
    global _background_task
    if _background_task and not _background_task.done():
        return
    _background_task = asyncio.create_task(background_polling_loop(bot))
