import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "/data/webhooks.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS webhook_jobs (
                id          TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                payload     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                attempts    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS webhook_attempts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id         TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status_code    INTEGER,
                error          TEXT,
                attempted_at   TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES webhook_jobs(id)
            )
        """)
        await db.commit()
