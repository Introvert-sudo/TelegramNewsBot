
import aiosqlite
import datetime
from typing import Optional, TypedDict

DB_PATH = "news_bot.db"


class UserRecord(TypedDict, total=False):
    telegram_id: int
    last_sent: Optional[datetime.datetime]


class UserWithSubscription(UserRecord):
    subscribed: bool


# === Initialization ===
async def init_db() -> None:
    """
    Initialize the SQLite database and ensure required tables exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                last_sent TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                telegram_id INTEGER PRIMARY KEY,
                active INTEGER DEFAULT 1
            )
            """
        )
        await db.commit()


# === User management ===
async def upsert_user(telegram_id: int) -> None:
    """
    Create user record if missing. Does nothing if already exists.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id) VALUES (?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id,),
        )
        await db.commit()


async def get_user(telegram_id: int) -> Optional[UserRecord]:
    """
    Retrieve a user record by telegram_id.
    Returns None if user does not exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT telegram_id, last_sent FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None

        last_sent: Optional[datetime.datetime] = None
        if row[1]:
            try:
                last_sent = datetime.datetime.fromisoformat(row[1])
            except Exception:
                last_sent = None  # malformed timestamp fallback

        return {"telegram_id": row[0], "last_sent": last_sent}


# === Subscription management ===
async def set_subscription_active(telegram_id: int, active: bool) -> None:
    """
    Enable or disable news subscription for a user.
    Inserts or updates the subscriptions table.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions (telegram_id, active)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET active=excluded.active
            """,
            (telegram_id, 1 if active else 0),
        )
        await db.commit()


async def is_subscribed(telegram_id: int) -> bool:
    """
    Return True if the user has an active subscription, False otherwise.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT active FROM subscriptions WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0] == 1)


async def list_subscribed_users() -> list[int]:
    """
    Return list of telegram IDs who currently have an active subscription.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT telegram_id FROM subscriptions WHERE active = 1")
        rows = await cur.fetchall()
        return [row[0] for row in rows]


# === Last sent tracking ===
async def update_last_sent(telegram_id: int, dt: datetime.datetime) -> None:
    """
    Update the timestamp of the last sent article for this user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_sent = ? WHERE telegram_id = ?",
            (dt.isoformat(), telegram_id),
        )
        await db.commit()


async def get_last_sent(telegram_id: int) -> Optional[datetime.datetime]:
    """
    Fetch the datetime when the last article was sent to the user.
    Returns None if missing or malformed.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT last_sent FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        if row and row[0]:
            try:
                return datetime.datetime.fromisoformat(row[0])
            except Exception:
                return None
        return None


# === Combined helper ===
async def get_user_with_subscription(telegram_id: int) -> Optional[UserWithSubscription]:
    """
    Retrieve user record combined with subscription status.
    Returns None if user does not exist.
    """
    user = await get_user(telegram_id)
    if user is None:
        return None
    subscribed = await is_subscribed(telegram_id)
    result: UserWithSubscription = {
        "telegram_id": user["telegram_id"],
        "last_sent": user.get("last_sent"),
        "subscribed": subscribed,
    }
    return result
