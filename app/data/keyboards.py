from aiogram.types import *

# === Keyboard active builder ===
def build_settings_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_active:
        buttons.append(InlineKeyboardButton(text="Enable", callback_data="start_news"))
    else:
        buttons.append(InlineKeyboardButton(text="Disable", callback_data="stop_news"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

