import binascii
import io
import json
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.app import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def render(client):
    data = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(data, format="PNG")
    response = client.post("/api/render", files={"file": ("test.png", data.getvalue())})
    assert response.status_code == 200
    return response.json()


def test_full_device_lifecycle_and_cooldown(client):
    preview = render(client)
    assert client.post("/api/device/poll").status_code == 204
    response = client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]})
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    assert client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]}).status_code == 409
    job = client.post("/api/device/poll").json()
    frame = client.get(job["frame_url"]).content
    assert len(frame) == 30000
    assert binascii.crc32(frame) == job["crc32"]
    base = f"/api/device/jobs/{job_id}/result"
    assert client.post(base, json={"status": "completed"}).status_code == 409
    assert client.post(base, json={"status": "refreshing"}).status_code == 200
    assert client.post(base, json={"status": "completed"}).status_code == 200
    assert client.post("/api/device/poll").status_code == 204
    status = client.get("/api/status").json()
    assert status["job"]["status"] == "completed"
    assert status["cooldown_seconds"] > 0
    assert client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]}).status_code == 409


def test_offline_and_expired_previews(client):
    preview = render(client)
    assert client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]}).status_code == 409
    assert client.post("/api/display-jobs", json={"preview_id": "missing"}).status_code == 410


def test_failed_download_preserves_no_refresh_cooldown(client):
    preview = render(client)
    client.post("/api/device/poll")
    job_id = client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]}).json()["job_id"]
    client.post("/api/device/poll")
    response = client.post(f"/api/device/jobs/{job_id}/result", json={"status": "failed", "error": "incomplete frame"})
    assert response.status_code == 200
    status = client.get("/api/status").json()
    assert status["job"]["error"] == "incomplete frame"
    assert status["cooldown_seconds"] == 0


def test_invalid_upload_and_options(client):
    assert client.post("/api/render", files={"file": ("bad.png", b"bad")}).status_code == 422
    assert client.post("/api/render", files={"file": ("bad.png", b"bad")}, data={"options": json.dumps({"brightness": 100})}).status_code == 422
    assert client.post("/api/render", files={"file": ("large.png", b"0" * (10 * 1024 * 1024 + 1))}).status_code == 413
    assert client.post("/api/render", files={"file": ("bad.png", b"bad")}, data={"options": '{"unknown":true}'}).status_code == 422


def test_connection_help_returns_addresses_without_credentials(client):
    data = client.get("/api/connection").json()
    assert isinstance(data["urls"], list)
    assert all(url.startswith("http://") and "@" not in url for url in data["urls"])


def test_service_restart_keeps_task_and_cooldown(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)
    preview = render(client)
    client.post("/api/device/poll")
    job_id = client.post("/api/display-jobs", json={"preview_id": preview["preview_id"]}).json()["job_id"]
    client.post("/api/device/poll")
    client.post(f"/api/device/jobs/{job_id}/result", json={"status": "refreshing"})
    restored = TestClient(create_app(tmp_path)).get("/api/status").json()
    assert restored["job"]["status"] == "refreshing"
    assert restored["cooldown_seconds"] > 0
    with closing(sqlite3.connect(tmp_path / "display.sqlite3")) as db:
        with db:
            db.execute("UPDATE job SET updated=0")
    assert client.get("/api/status").json()["job"]["status"] == "failed"
