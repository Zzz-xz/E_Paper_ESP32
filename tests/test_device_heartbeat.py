"""设备闲置失联时尽快阻止发送，面板刷新期间允许暂停轮询。"""
import pytest

from server.models import FRAME_BYTES
from server.storage import JobStore


@pytest.fixture
def device(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("server.storage.time.time", lambda: now[0])
    store = JobStore(tmp_path / "display.sqlite3")
    store.poll()
    return store, now


def test_idle_device_becomes_offline_and_cannot_accept_jobs(device):
    store, now = device
    now[0] += 10
    assert not store.status()["online"]
    with pytest.raises(ValueError, match="心跳已中断"):
        store.create(bytes(FRAME_BYTES), b"preview")
    store.poll()
    assert store.status()["online"]
    assert store.create(bytes(FRAME_BYTES), b"preview")


def test_panel_refresh_does_not_report_false_disconnect(device):
    store, now = device
    identifier = store.create(bytes(FRAME_BYTES), b"preview")
    store.poll()
    store.result(identifier, "refreshing", "")
    now[0] += 20
    assert store.status()["online"]
    store.result(identifier, "completed", "")
    assert store.status()["online"]
