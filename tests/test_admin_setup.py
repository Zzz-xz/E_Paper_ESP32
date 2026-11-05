import json
import secrets
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from server.admin import AdminAccess, set_password
from server.app import create_app


@pytest.fixture
def admin_client(tmp_path):
    password = secrets.token_urlsafe(20)
    set_password(tmp_path, password)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        yield client, password, tmp_path


def login(client, password):
    response = client.post('/api/admin/login', json={'password': password})
    assert response.status_code == 200
    return response


def test_password_is_salted_and_admin_session_expires_on_password_change(admin_client):
    client, password, directory = admin_client
    record = json.loads((directory / 'admin.json').read_text())
    assert password not in (directory / 'admin.json').read_text()
    assert record['iterations'] >= 600000
    response = login(client, password)
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/api/admin/status').json()['authenticated']
    set_password(directory, password)
    assert not client.get('/api/admin/status').json()['authenticated']


def test_normal_users_cannot_start_or_read_authorized_setup(admin_client):
    client, password, _ = admin_client
    assert client.post('/api/device/setup').status_code == 401
    assert client.get('/api/device/setup').status_code == 401
    assert client.post('/api/documents/render', json={'session_id': 'public-text', 'texts': []}).status_code == 200
    login(client, password)
    assert client.post('/api/device/setup').status_code == 409
    assert client.post('/api/device/poll', json={'setup_supported': True}).status_code == 204
    assert client.post('/api/device/setup').status_code == 202
    command = client.post('/api/device/poll', json={'setup_supported': True}).json()
    assert command['command'] == 'setup'
    token = secrets.token_hex(16)
    result = {'url': 'http://192.0.2.10', 'token': token}
    assert client.post(f"/api/device/setup/{command['command_id']}/result", json=result).status_code == 200
    authorized = client.get('/api/device/setup').json()
    assert authorized['url'].endswith('#token=' + token)
    public = client.get('/api/status').json()
    assert public['network_setup']['url'] == ''
    assert token not in json.dumps(public)
    assert client.post('/api/admin/logout').status_code == 200
    assert client.get('/api/device/setup').status_code == 401


def test_setup_ack_requires_valid_ip_and_token_and_expired_command_is_visible(admin_client):
    client, password, _ = admin_client
    login(client, password)
    client.post('/api/device/poll', json={'setup_supported': True})
    client.post('/api/device/setup')
    command = client.post('/api/device/poll', json={'setup_supported': True}).json()
    path = f"/api/device/setup/{command['command_id']}/result"
    for result in ({'url': 'javascript:alert(1)'}, {'url': 'http://192.0.2.10'}, {'url': 'http://user:pass@192.0.2.10', 'token': secrets.token_hex(16)}):
        assert client.post(path, json=result).status_code == 422
    client.app.state.setup._created -= 31
    assert client.get('/api/device/setup').json()['state'] == 'failed'


def test_wrong_password_has_bounded_attempts_and_no_default_password(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert not client.get('/api/admin/status').json()['configured']
        assert client.post('/api/admin/login', json={'password': 'unused-credential'}).status_code == 503
    password = secrets.token_urlsafe(20)
    set_password(tmp_path, password)
    access = AdminAccess(tmp_path)
    for _ in range(5):
        with pytest.raises(PermissionError):
            access.login('incorrect')
    with pytest.raises(PermissionError, match='60'):
        access.login(password)


def test_display_tasks_are_not_interrupted_by_setup(admin_client):
    client, password, _ = admin_client
    login(client, password)
    client.post('/api/device/poll', json={'setup_supported': True})
    preview = client.post('/api/documents/render', json={'session_id': 'active', 'texts': []}).json()
    assert client.post('/api/display-jobs', json={'preview_id': preview['preview_id']}).status_code == 201
    assert client.post('/api/device/setup').status_code == 409


def test_recovery_role_only_resets_admin_and_invalidates_old_session(admin_client):
    client, password, directory = admin_client
    recovery_password = secrets.token_urlsafe(20)
    set_password(directory, recovery_password, "recovery")
    login(client, password)
    assert client.post('/api/recovery/reset-admin', json={'new_password': secrets.token_urlsafe(20)}).status_code == 401
    with TestClient(client.app) as superadmin:
        assert superadmin.post('/api/recovery/login', json={'password': recovery_password}).status_code == 200
        assert superadmin.post('/api/device/setup').status_code == 401
        assert superadmin.get('/api/device/setup').status_code == 401
        assert superadmin.post('/api/recovery/reset-admin', json={'new_password': recovery_password}).status_code == 422
        new_password = secrets.token_urlsafe(20)
        assert superadmin.post('/api/recovery/reset-admin', json={'new_password': new_password}).status_code == 200
        assert not client.get('/api/admin/status').json()['authenticated']
        assert client.post('/api/admin/login', json={'password': password}).status_code == 401
        login(client, new_password)
        assert superadmin.post('/api/recovery/logout').status_code == 200
        assert superadmin.post('/api/recovery/reset-admin', json={'new_password': secrets.token_urlsafe(20)}).status_code == 401


def test_fixed_recovery_password_is_not_overwritten_by_cli(tmp_path):
    set_password(tmp_path, secrets.token_urlsafe(20), "recovery")
    before = (tmp_path / 'recovery.json').read_bytes()
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'server.admin', '--recovery'],
                            env={**os.environ, 'EPAPER_DATA_DIR': str(tmp_path)}, capture_output=True, timeout=5)
    assert result.returncode != 0
    assert (tmp_path / 'recovery.json').read_bytes() == before


def test_reset_password_length_is_eight_to_thirty_two(admin_client):
    client, _, directory = admin_client
    recovery_password = secrets.token_urlsafe(20)
    set_password(directory, recovery_password, 'recovery')
    assert client.post('/api/recovery/login', json={'password': recovery_password}).status_code == 200
    for length, expected in ((7, 422), (8, 200), (32, 200), (33, 422)):
        value = secrets.token_hex(20)[:length]
        assert client.post('/api/recovery/reset-admin', json={'new_password': value}).status_code == expected
