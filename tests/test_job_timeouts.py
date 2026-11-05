"""下载重复轮询不能续期，下载期限与真实面板刷新期限独立。"""
import pytest

from server.models import FRAME_BYTES
from server.storage import JobStore


@pytest.fixture
def state(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("server.storage.time.time", lambda: now[0])
    store = JobStore(tmp_path / "display.sqlite3")
    store.poll()
    identifier = store.create(bytes(FRAME_BYTES), b"preview")
    return store, identifier, now


def test_unclaimed_task_fails_after_fifteen_seconds(state):
    store, _, now = state
    now[0] += 15.01
    assert store.status()["job"]["status"] == "failed"
    assert "接收任务超时" in store.status()["job"]["error"]


def test_repeated_download_poll_does_not_extend_deadline(state):
    store, identifier, now = state
    assert store.poll() == identifier
    started = store.status()["job"]["updated"]
    for _ in range(22):
        now[0] += 2
        assert store.poll() == identifier
        assert store.status()["job"]["updated"] == started
    now[0] += 1.01
    assert store.poll() is None
    assert "下载图片超时" in store.status()["job"]["error"]
    with pytest.raises(ValueError, match="状态不匹配"):
        store.result(identifier, "refreshing", "")


def test_refresh_has_independent_panel_deadline(state):
    store, identifier, now = state
    store.poll()
    now[0] += 5
    store.result(identifier, "refreshing", "")
    now[0] += 119
    assert store.status()["job"]["status"] == "refreshing"
    now[0] += 1.01
    assert "刷新屏幕超时" in store.status()["job"]["error"]


def test_late_refresh_is_rejected_without_browser_status_poll(state):
    store, identifier, now = state
    store.poll()
    now[0] += 45.01
    with pytest.raises(ValueError, match="状态不匹配"):
        store.result(identifier, "refreshing", "")
