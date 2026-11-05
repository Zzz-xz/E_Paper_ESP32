"""连接指南使用实际访问入口，并在刷新时重新读取电脑地址。"""
import socket

from fastapi.testclient import TestClient

from server.app import create_app


def _addresses(*values):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 0)) for value in values]


def test_current_access_host_and_port_are_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: _addresses("192.0.2.20", "198.51.100.1"))
    with TestClient(create_app(tmp_path)) as client:
        for host in ("192.0.2.20:8123", "198.51.100.42:9001", "epaper.example:8000"):
            response = client.get("/api/connection", headers={"host": host})
            data = response.json()
            assert data["preferred_url"] == f"http://{host}"
            assert data["urls"][0] == data["preferred_url"]
            assert response.headers["cache-control"] == "no-store"


def test_local_access_rereads_interfaces_without_recommending_loopback(tmp_path, monkeypatch):
    addresses = ["192.0.2.20", "127.0.0.1", "169.254.1.1"]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: _addresses(*addresses))
    with TestClient(create_app(tmp_path), base_url="http://localhost:8123") as client:
        first = client.get("/api/connection").json()
        assert first["preferred_url"] == ""
        assert first["urls"] == ["http://192.0.2.20:8123"]
        addresses[:] = ["198.51.100.42"]
        second = client.get("/api/connection").json()
        assert second["preferred_url"] == ""
        assert second["urls"] == ["http://198.51.100.42:8123"]


def test_current_working_url_survives_interface_lookup_failure(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError("no interface lookup")

    monkeypatch.setattr(socket, "getaddrinfo", unavailable)
    with TestClient(create_app(tmp_path), base_url="http://192.0.2.20:8123") as client:
        data = client.get("/api/connection").json()
        assert data["urls"] == ["http://192.0.2.20:8123"]
        assert data["preferred_url"] == "http://192.0.2.20:8123"
        assert data["message"]
