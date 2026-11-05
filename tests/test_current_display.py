"""只展示设备确认画面，覆盖持久化、替换任务和独立的查看冷却。"""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.app import create_app
from server.models import FRAME_BYTES
from server.storage import DisplayReadCooling, JobStore


def complete(store, png):
    store.poll()
    job_id = store.create(bytes(FRAME_BYTES), png)
    store.poll()
    store.result(job_id, "refreshing", "")
    store.result(job_id, "completed", "")
    return job_id


def allow_next_refresh(store):
    with store.connect() as db:
        db.execute("UPDATE meta SET value=0 WHERE key='cooldown_until'")


def test_public_api_returns_confirmed_png_and_limits_repeated_reads(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/display/current").status_code == 404
        png = io.BytesIO()
        Image.new("RGB", (400, 300), "red").save(png, format="PNG")
        job_id = complete(app.state.store, png.getvalue())
        response = client.get("/api/display/current")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        snapshot = response.json()
        assert snapshot["job_id"] == job_id
        assert snapshot["png"] == "data:image/png;base64," + base64.b64encode(png.getvalue()).decode("ascii")
        assert snapshot["confirmed_at"] > 0
        assert snapshot["cooldown_seconds"] == 5
        limited = client.get("/api/display/current")
        assert limited.status_code == 429
        assert 1 <= int(limited.headers["retry-after"]) <= 5


def test_last_confirmed_picture_survives_pending_failed_tasks_and_restart(tmp_path):
    path = tmp_path / "display.sqlite3"
    store = JobStore(path)
    first = complete(store, b"first-confirmed")
    original = store.current_display()
    allow_next_refresh(store)
    next_job = store.create(bytes(FRAME_BYTES), b"not-confirmed")
    assert JobStore(path).current_display() == original
    store.poll()
    store.result(next_job, "failed", "incomplete download")
    assert JobStore(path).current_display()["job_id"] == first
    complete(store, b"next-confirmed")
    assert JobStore(path).current_display()["png"] == b"next-confirmed"


def test_existing_completed_job_is_available_on_upgrade(tmp_path):
    path = tmp_path / "display.sqlite3"
    store = JobStore(path)
    job_id = complete(store, b"legacy-confirmed")
    with store.connect() as db:
        db.execute("DROP TABLE displayed")
    snapshot = JobStore(path).current_display()
    assert snapshot["job_id"] == job_id
    assert snapshot["png"] == b"legacy-confirmed"


def test_read_cooldown_is_five_seconds_and_does_not_change_refresh_cooldown(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "display.sqlite3")
    complete(store, b"confirmed")
    now = [100.0]
    monkeypatch.setattr("server.storage.time.monotonic", lambda: now[0])
    store.current_display()
    now[0] = 104.999
    with pytest.raises(DisplayReadCooling):
        store.current_display()
    now[0] = 105
    assert store.current_display()["png"] == b"confirmed"
    assert 0 < store.status()["cooldown_seconds"] <= 30
