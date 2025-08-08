import logging
from app.data import keyboards as kb
from aiogram.exceptions import TelegramBadRequest

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app import news_parser
from app.data import db

logger = logging.getLogger(__name__)
router = Router()



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
        await db.init_db()  # Ensure the database is initialized before proceeding

        user_id = message.from_user.id  # Get the Telegram user ID of the sender

        # Check if the user already exists in the database
        existing = await db.get_user(user_id)
        print(existing)
        if not existing:
            # If the user does not exist, create a new user record
            await db.upsert_user(user_id)

        # If previous sources message exists, edit it instead of deleting
        if user_id in _last_intro_message:
            chat_id, msg_id = _last_intro_message[user_id]
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="Choose your sources below.",
                    reply_markup=None
                )
            except TelegramBadRequest:
                pass  # Message might have already been deleted or can't be edited

        # Build the sources keyboard
        mark_up = await kb.build_sources_keyboard(user_id)

        if mark_up is None:
            await message.answer("No sources found. Please contact the administrator.")
            return

        # Send a new message with the sources keyboard
        reply = await message.answer(
            "Do you want to receive the latest news? Choose your sources below.",
            reply_markup=mark_up,
        )

        # Store the chat and message ID of this prompt so it can be edited later
        _last_intro_message[user_id] = (reply.chat.id, reply.message_id)
    except Exception:
        # Log any exception that occurs and notify the user of the error
        logger.exception("Error in /start handler")
        await message.answer("An error occurred during setup. Please try again later.")


@router.message(Command("sources"))
async def show_sources(message: Message):
    user_id = message.from_user.id
    user_db = await db.get_user(user_id)
    if not user_db:
        await db.add_user(user_id)
        user_db = await db.get_user(user_id)
    user_db_id = user_db["id"]

    # If there is a previous sources message, edit it instead of sending a new one
    if user_id in _last_intro_message:
        chat_id, msg_id = _last_intro_message[user_id]
        try:
            await message.bot.edit_message_text(
                "Choose your source below.",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=None
            )
        except TelegramBadRequest:
            pass  # Message might have already been deleted or can't be edited
    
    keyboard = await kb.build_sources_keyboard(user_db_id)
    reply = await message.answer("Select your sources:", reply_markup=keyboard)
    _last_intro_message[user_id] = (reply.chat.id, reply.message_id)


@router.callback_query(lambda c: c.data.startswith("source_") and not c.data.startswith("source_latest_"))
async def handle_toggle_source(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    try:
        source_id = int(data.split("_")[-1])
    except Exception:
        await callback_query.answer("Invalid source.", show_alert=True)
        return

    # Get user DB id (not Telegram id)
    user_db = await db.get_user(user_id)
    if not user_db:
        await db.add_user(user_id)
        user_db = await db.get_user(user_id)
    user_db_id = user_db["id"]

    # Check if user is already subscribed
    subscription = await db.get_subscription(user_db_id, source_id)
    if subscription:
        # Unsubscribe
        await db.delete_subscription(user_db_id, source_id)
        action = "unsubscribed from"
    else:
        # Subscribe
        await db.add_subscription(user_db_id, source_id)
        action = "subscribed to"

    # Update the keyboard
    keyboard = await kb.build_sources_keyboard(user_db_id)
    try:
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        pass  # Message might have been deleted or can't be edited

    # Notify the user
    source = await db.get_source_by_id(source_id)
    source_name = source["name"] if source else f"ID {source_id}"
    await callback_query.answer(f"You have {action} {source_name}.", show_alert=False)




@router.message(Command("latest"))
async def cmd_lattest(message: Message):
    """
    Handle /latest: show a list of all sources as inline buttons.
    """

    keyboard = await kb.build_all_sources_keyboard()
    if keyboard is None:
        await message.answer("No sources found. Please contact the administrator.")
        return
    await message.answer("Choose a source to get the latest news:", reply_markup=keyboard)


def build_latest_news_message(latest: dict) -> str:
    """
    Build a formatted HTML message for the latest news item.
    """

    # Extract fields with defaults
    title = latest.get("title", "")
    link = latest.get("link", "")
    summary = latest.get("summary", "")
    published = latest.get("published", "")

    # Start building the message
    msg = f"<b>{title}</b>\n"
    if published:
        msg += f"<i>{published}</i>\n"
    if summary:
        msg += f"\n{summary}\n"
    if link:
        msg += f"\n<a href=\"{link}\">Read more</a>"
    return msg

@router.callback_query(lambda c: c.data.startswith("source_latest_"))
async def handle_lattest_source(callback_query: CallbackQuery):
    # Parse the source ID from the callback data
    source_id = int(callback_query.data.split("_")[-1])

    # Retrieve the source from the database
    source = await db.get_source_by_id(source_id)
    if not source:
        await callback_query.answer("Source not found.", show_alert=True)
        return

    # Fetch the latest news for the source
    latest = await news_parser.get_latest(source["url"])
    if not latest:
        await callback_query.message.answer(f"No news found for {source['name']}.")
        await callback_query.answer()
        return

    # Build the message using the helper function
    msg = build_latest_news_message(latest)

    # Send the formatted message to the user
    await callback_query.message.answer(msg, parse_mode="HTML", disable_web_page_preview=False)
    await callback_query.answer()


