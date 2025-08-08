
from app.data import db as db_module
import asyncio
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.data import db as db_module


# === Keyboard active builder ===
def build_settings_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_active:
        buttons.append(InlineKeyboardButton(text="Enable", callback_data="start_news"))
    else:
        buttons.append(InlineKeyboardButton(text="Disable", callback_data="stop_news"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def build_sources_keyboard(user_id: int):
    """
    Build an inline keyboard with all sources, marking those the user is subscribed to.
    """
    async with db_module.aiosqlite.connect(db_module.DB_PATH) as conn:
        cursor = await conn.execute("SELECT id, name FROM source ORDER BY name")
        sources = await cursor.fetchall()

        # Get user's active subscriptions
        cursor = await conn.execute("SELECT source_id FROM user_source WHERE user_id = ?", (user_id,))
        active_sources = {row[0] for row in await cursor.fetchall()}

    if not sources:
        return None

    buttons = [
        [InlineKeyboardButton(
            text=(f"✅ {name}" if src_id in active_sources else name),
            callback_data=f"source_{src_id}"
        )]
        for src_id, name in sources
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_all_sources_keyboard():
    """
    Build an inline keyboard with all sources as buttons (no active marking).
    """
    async with db_module.aiosqlite.connect(db_module.DB_PATH) as conn:
        cursor = await conn.execute("SELECT id, name FROM source ORDER BY name")
        sources = await cursor.fetchall()

    if not sources:
        return None

    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"source_latest_{src_id}")]
        for src_id, name in sources
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)