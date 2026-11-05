"""网页口令入口的权限回归，不使用真实部署的密码或数据目录。"""
import secrets

from fastapi.testclient import TestClient

from server.app import create_app


def local_client(app):
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def test_loopback_can_initialize_distinct_passwords_once(tmp_path):
    app = create_app(tmp_path)
    admin, recovery = secrets.token_urlsafe(15), secrets.token_urlsafe(15)
    with local_client(app) as client:
        assert client.get("/api/security/status").json()["initialization_allowed"]
        assert client.post("/api/admin/initialize", json={"new_password": admin}).status_code == 201
        assert client.post("/api/recovery/initialize", json={"new_password": admin}).status_code == 422
        assert client.post("/api/recovery/initialize", json={"new_password": recovery}).status_code == 201
        assert client.post("/api/admin/initialize", json={"new_password": secrets.token_urlsafe(15)}).status_code == 409
        assert client.post("/api/recovery/initialize", json={"new_password": secrets.token_urlsafe(15)}).status_code == 409
        assert admin not in (tmp_path / "admin.json").read_text()
        assert recovery not in (tmp_path / "recovery.json").read_text()
        assert client.post("/api/admin/login", json={"password": admin}).status_code == 200
        assert client.post("/api/recovery/login", json={"password": recovery}).status_code == 200


def test_remote_clients_and_forged_hosts_cannot_initialize_passwords(tmp_path):
    app = create_app(tmp_path)
    cases = [("http://192.0.2.1", "192.0.2.10"), ("http://localhost", "192.0.2.10"),
             ("http://untrusted.example", "127.0.0.1")]
    for base_url, host in cases:
        with TestClient(app, base_url=base_url, client=(host, 50000)) as client:
            assert not client.get("/api/security/status").json()["initialization_allowed"]
            for role in ("admin", "recovery"):
                response = client.post(f"/api/{role}/initialize", json={"new_password": secrets.token_urlsafe(15)},
                                       headers={"X-Forwarded-For": "127.0.0.1"})
                assert response.status_code == 403
    assert not (tmp_path / "admin.json").exists()
    assert not (tmp_path / "recovery.json").exists()


def test_admin_can_change_password_but_public_and_recovery_roles_cannot(tmp_path):
    app = create_app(tmp_path)
    admin, recovery, replacement = (secrets.token_urlsafe(15) for _ in range(3))
    with local_client(app) as owner:
        owner.post("/api/admin/initialize", json={"new_password": admin})
        owner.post("/api/recovery/initialize", json={"new_password": recovery})
        assert owner.post("/api/admin/password", json={"new_password": replacement}).status_code == 401
        owner.post("/api/recovery/login", json={"password": recovery})
        assert owner.post("/api/admin/password", json={"new_password": replacement}).status_code == 401
        assert owner.post("/api/device/setup").status_code == 401
        owner.post("/api/admin/login", json={"password": admin})
        with local_client(app) as another:
            another.post("/api/admin/login", json={"password": admin})
            assert owner.post("/api/admin/password", json={"new_password": recovery}).status_code == 422
            assert owner.post("/api/admin/password", json={"new_password": "short"}).status_code == 422
            assert owner.post("/api/admin/password", json={"new_password": replacement}).status_code == 200
            assert not owner.get("/api/admin/status").json()["authenticated"]
            assert not another.get("/api/admin/status").json()["authenticated"]
        assert owner.post("/api/admin/login", json={"password": admin}).status_code == 401
        assert owner.post("/api/admin/login", json={"password": replacement}).status_code == 200
        assert owner.post("/api/recovery/password", json={"new_password": replacement}).status_code == 404
        assert owner.post("/api/documents/render", json={"session_id": "public-use", "texts": []}).status_code == 200
