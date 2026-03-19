"""
E2E Happy Path Test
===================
Scenariusz:
  1. Wyślij zlecenie webhook do lokalnego httpbin (/post).
  2. API natychmiast zwraca 202 + job_id.
  3. Worker dostarcza webhook w tle — oczekujemy statusu "delivered"
     w ciągu 10 sekund (polling co 0.5s).
  4. GET /webhooks/{job_id} zwraca historię z co najmniej jedną próbą
     ze status_code 200.

Założenia:
  - Środowisko uruchomione przez: docker compose up --build -d
  - API dostępne pod http://localhost:8000
  - httpbin dostępne pod http://localhost:8080 (alias wewnętrzny: httpbin)
  - Testy uruchamiamy: pytest tests/test_e2e.py -v
"""

import time
import pytest
import httpx

API = "http://localhost:8000"
# wewnętrzna nazwa serwisu w sieci Docker Compose
TARGET = "http://httpbin/post"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=API, timeout=15) as c:
        yield c


def test_happy_path(client):
    payload = {"event": "order.created", "order_id": 42}

    # 1. Submit
    resp = client.post("/webhooks/", json={"url": TARGET, "payload": payload})
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["status"] == "accepted"
    job_id = data["job_id"]

    # 2. Poll until delivered (max 10s)
    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        r = client.get(f"/webhooks/{job_id}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status == "delivered":
            break
        time.sleep(0.5)

    assert status == "delivered", f"Job still in status: {status}"

    # 3. Verify attempt history
    detail = client.get(f"/webhooks/{job_id}").json()
    assert len(detail["history"]) >= 1
    assert detail["history"][0]["status_code"] == 200


def test_deduplication(client):
    payload = {"event": "dedup_test"}
    body = {"url": TARGET, "payload": payload}

    resp1 = client.post("/webhooks/", json=body)
    assert resp1.status_code == 202
    assert resp1.json()["status"] == "accepted"

    resp2 = client.post("/webhooks/", json=body)
    assert resp2.status_code == 202
    assert resp2.json()["status"] == "ignored"


def test_list_jobs(client):
    resp = client.get("/webhooks/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) > 0
