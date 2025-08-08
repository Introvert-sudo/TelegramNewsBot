import aiosqlite

DB_PATH = "news_bot.db"


# === Initialization ===
async def init_db() -> None:
    """
    Initialize the SQLite database and ensure required tables exist.
    Creates:
      - user: id (PK), telegram_id (unique)
      - source: id (PK), url (unique)
      - user_source: user_id, source_id, latest_post_time
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Create the 'user' table if it doesn't exist.
        # This table stores each Telegram user by a unique integer ID and their Telegram ID.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL
            )
            """
        )
        # Create the 'source' table if it doesn't exist.
        # This table stores each news source URL with a unique integer ID.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS source (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL
            )
            """
        )
        # Create the 'user_source' table if it doesn't exist.
        # This table links users to sources and tracks the latest post time sent to each user.
        # - user_id: references the 'user' table
        # - source_id: references the 'source' table
        # - latest_post_time: ISO string of the last post sent to the user for this source
        # The combination of user_id and source_id is the primary key.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_source (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                latest_post_time TEXT,
                UNIQUE (user_id, source_id),
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (source_id) REFERENCES source(id) ON DELETE CASCADE
            )
            """
        )
        # Commit all table creation statements to the database.
        await db.commit()




# === User management ===

async def upsert_user(telegram_id: int) -> None:
    """
    Create user record if missing. Does nothing if already exists.
    """
    # Open a connection to the SQLite database
    async with aiosqlite.connect(DB_PATH) as db:
        # Attempt to insert a new user with the given telegram_id.
        # If a user with this telegram_id already exists, do nothing (no-op).
        await db.execute(
            """
            INSERT INTO user (telegram_id) VALUES (?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id,),
        )
        # Commit the transaction to persist changes.
        await db.commit()


async def get_user(telegram_id: int) -> dict | None:
    """
    Retrieve a user record by telegram_id.
    Returns None if user does not exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, telegram_id FROM user WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None

        return {"telegram_id": row[0], "id": row[1]}


# === Subscription management ===

async def add_subscription(user_id: int, source_id: int, latest_post_time: str = None) -> None:
    """
    Add or update a subscription for a user to a source.
    If the subscription exists, update the latest_post_time.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_source (user_id, source_id, latest_post_time)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, source_id) DO UPDATE SET latest_post_time=excluded.latest_post_time
            """,
            (user_id, source_id, latest_post_time)
        )
        await db.commit()


async def get_subscription(user_id: int, source_id: int) -> dict | None:
    """
    Retrieve a specific subscription for a user and source.
    Returns a dict with id, user_id, source_id, latest_post_time or None if not found.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, user_id, source_id, latest_post_time
            FROM user_source
            WHERE user_id = ? AND source_id = ?
            """,
            (user_id, source_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "source_id": row[2],
                    "latest_post_time": row[3]
                }
            return None


async def delete_subscription(user_id: int, source_id: int) -> None:
    """
    Delete a subscription for a user to a source.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            DELETE FROM user_source
            WHERE user_id = ? AND source_id = ?
            """,
            (user_id, source_id)
        )
        await db.commit()

async def get_all_subscriptions() -> list[dict]:
    """
    Get all user subscriptions with id, user_id, source_id, latest_post_time.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, user_id, source_id, latest_post_time FROM user_source"
        )
        rows = await cursor.fetchall()
        return [
            {"id": row[0], "user_id": row[1], "source_id": row[2], "latest_post_time": row[3]} for row in rows
        ]

async def update_subscription_last_post_time_by_id(sub_id: int, last_post_time: str) -> None:
    """
    Update the latest_post_time for a subscription by its unique id.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_source SET latest_post_time = ? WHERE id = ?",
            (last_post_time, sub_id)
        )
        await db.commit()



# === Source management ===

async def add_source(name: str, url: str) -> int | None:
    """
    Add a new source to the database. Returns the source ID, or None if failed.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO source (name, url) VALUES (?, ?)",
            (name, url)
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT id FROM source WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_source_by_id(source_id: int) -> dict | None:
    """
    Get a source by its ID.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, url FROM source WHERE id = ?",
            (source_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "url": row[2]}
        return None

async def get_source_by_url(url: str) -> dict | None:
    """
    Get a source by its URL.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, url FROM source WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "url": row[2]}
        return None

async def get_source_by_name(name: str) -> dict | None:
    """
    Get a source by its name.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, url FROM source WHERE name = ?",
            (name,)
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "url": row[2]}
        return None


async def delete_source(source_id: int) -> None:
    """
    Delete a source by its ID.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM source WHERE id = ?",
            (source_id,)
        )
        await db.commit()

async def get_all_sources() -> list[dict]:
    """
    Get all sources.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, url FROM source"
        )
        rows = await cursor.fetchall()
        return [{"id": row[0], "name": row[1], "url": row[2]} for row in rows]