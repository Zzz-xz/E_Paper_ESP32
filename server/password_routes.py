"""网页口令设置入口：本机初始化、管理员改密、固定恢复口令。"""
from fastapi import Depends, HTTPException, Request, Response

from .admin import initialize_password, set_password
from .models import NewAdminPassword

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}


def _local_initialization(request: Request):
    return bool(request.client and request.client.host in LOOPBACK_CLIENTS
                and request.url.hostname in LOOPBACK_HOSTS)


def _require_local_initialization(request: Request):
    if not _local_initialization(request):
        raise HTTPException(403, "首次设置请在运行网站的电脑上，通过 localhost 或 127.0.0.1 打开工作台。")


def register_password_routes(app, admin, recovery, require_admin):
    @app.get("/api/security/status")
    def status(request: Request):
        return {"admin_configured": admin.configured(), "recovery_configured": recovery.configured(),
                "initialization_allowed": _local_initialization(request)}

    def initialize(access, credentials, role):
        if access.configured():
            raise HTTPException(409, "此口令已经设置，首次设置入口不能覆盖已有口令。")
        try:
            initialize_password(access.path.parent, credentials.new_password, role)
        except FileExistsError as error:
            raise HTTPException(409, "此口令已经设置，请刷新管理状态。") from error
        return {"ok": True}

    @app.post("/api/admin/initialize", dependencies=[Depends(_require_local_initialization)], status_code=201)
    def initialize_admin(credentials: NewAdminPassword):
        return initialize(admin, credentials, "admin")

    @app.post("/api/recovery/initialize", dependencies=[Depends(_require_local_initialization)], status_code=201)
    def initialize_recovery(credentials: NewAdminPassword):
        return initialize(recovery, credentials, "recovery")

    @app.post("/api/admin/password", dependencies=[Depends(require_admin)])
    def change_admin_password(credentials: NewAdminPassword, response: Response):
        set_password(admin.path.parent, credentials.new_password)
        response.delete_cookie("epaper_admin", path="/api")
        return {"ok": True}
