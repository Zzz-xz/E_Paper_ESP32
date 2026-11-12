"""刷新开始后按 30 秒计时，完成回报不延长冷却。"""
import pytest

from server.models import FRAME_BYTES
from server.storage import JobStore


def test_next_refresh_is_allowed_after_thirty_seconds(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("server.storage.time.time", lambda: now[0])
    store = JobStore(tmp_path / "display.sqlite3")
    store.poll()
    job_id = store.create(bytes(FRAME_BYTES), b"preview")
    store.poll()
    store.result(job_id, "refreshing", "")
    assert store.status()["cooldown_seconds"] == 30
    now[0] += 10
    store.result(job_id, "completed", "")
    assert store.status()["cooldown_seconds"] == 20
    now[0] = 1029.999
    store.poll()
    with pytest.raises(ValueError, match="冷却"):
        store.create(bytes(FRAME_BYTES), b"preview")
    now[0] = 1030
    assert store.status()["cooldown_seconds"] == 0
    store.create(bytes(FRAME_BYTES), b"next-preview")
