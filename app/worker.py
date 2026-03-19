import asyncio
import json
import os
from datetime import datetime, timezone

import aiosqlite
import httpx

from app.database import DB_PATH
from app.queue import job_queue

MAX_ATTEMPTS = 3
CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "5"))
_semaphore: asyncio.Semaphore | None = None
_task: asyncio.Task | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _deliver(job_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM webhook_jobs WHERE id=?", (job_id,)) as cur:
            job = await cur.fetchone()
        if not job:
            return

        url = job["url"]
        payload = json.loads(job["payload"])
        attempts_done = job["attempts"]

    for attempt in range(attempts_done + 1, MAX_ATTEMPTS + 1):
        status_code = None
        error = None
        success = False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                status_code = resp.status_code
                success = 200 <= status_code < 300
        except Exception as exc:
            error = str(exc)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO webhook_attempts
                   (job_id, attempt_number, status_code, error, attempted_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, attempt, status_code, error, _now()),
            )
            if success:
                new_status = "delivered"
            elif attempt >= MAX_ATTEMPTS:
                new_status = "failed"
            else:
                new_status = "retrying"

            await db.execute(
                "UPDATE webhook_jobs SET status=?, attempts=?, updated_at=? WHERE id=?",
                (new_status, attempt, _now(), job_id),
            )
            await db.commit()

        if success:
            return

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(2 ** attempt)


async def _run_with_semaphore(job_id: str):
    async with _semaphore:
        await _deliver(job_id)


async def _worker_loop():
    global _semaphore
    _semaphore = asyncio.Semaphore(CONCURRENCY)

    # Re-enqueue jobs that survived a restart
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM webhook_jobs WHERE status IN ('pending', 'retrying')"
        ) as cur:
            rows = await cur.fetchall()
    for row in rows:
        await job_queue.put(row["id"])

    while True:
        job_id = await job_queue.get()
        asyncio.create_task(_run_with_semaphore(job_id))


async def start_worker():
    global _task
    _task = asyncio.create_task(_worker_loop())


async def stop_worker():
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
