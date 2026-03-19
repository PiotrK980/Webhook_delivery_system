import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.database import DB_PATH
from app.models import WebhookRequest, WebhookJob, WebhookJobDetail, WebhookAttempt
from app.queue import job_queue
from app.dedup import is_duplicate, mark_seen

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/", status_code=202)
async def submit_webhook(req: WebhookRequest):
    url = str(req.url)
    payload_str = json.dumps(req.payload, sort_keys=True)

    if await is_duplicate(url, payload_str):
        return {"status": "ignored", "reason": "duplicate within 10s window"}

    await mark_seen(url, payload_str)

    job_id = str(uuid.uuid4())
    now = _now()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO webhook_jobs
               (id, url, payload, status, attempts, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, url, payload_str, "pending", 0, now, now),
        )
        await db.commit()

    await job_queue.put(job_id)
    return {"job_id": job_id, "status": "accepted"}


@router.get("/", response_model=list[WebhookJob])
async def list_jobs():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM webhook_jobs ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [
        WebhookJob(
            id=r["id"],
            url=r["url"],
            payload=json.loads(r["payload"]),
            status=r["status"],
            attempts=r["attempts"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/{job_id}", response_model=WebhookJobDetail)
async def get_job(job_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM webhook_jobs WHERE id=?", (job_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        async with db.execute(
            "SELECT * FROM webhook_attempts WHERE job_id=? ORDER BY attempt_number",
            (job_id,),
        ) as cur:
            attempts = await cur.fetchall()

    history = [
        WebhookAttempt(
            id=a["id"],
            job_id=a["job_id"],
            attempt_number=a["attempt_number"],
            status_code=a["status_code"],
            error=a["error"],
            attempted_at=a["attempted_at"],
        )
        for a in attempts
    ]
    return WebhookJobDetail(
        id=row["id"],
        url=row["url"],
        payload=json.loads(row["payload"]),
        status=row["status"],
        attempts=row["attempts"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        history=history,
    )
