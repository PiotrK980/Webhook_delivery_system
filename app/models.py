from pydantic import BaseModel, HttpUrl
from typing import Any, Optional


class WebhookRequest(BaseModel):
    url: HttpUrl
    payload: dict[str, Any]


class WebhookJob(BaseModel):
    id: str
    url: str
    payload: dict[str, Any]
    status: str
    attempts: int
    created_at: str
    updated_at: str


class WebhookAttempt(BaseModel):
    id: int
    job_id: str
    attempt_number: int
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempted_at: str


class WebhookJobDetail(WebhookJob):
    history: list[WebhookAttempt]
