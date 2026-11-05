import binascii
import base64
import os
import socket
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response as FastResponse, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import AdminLogin, DeviceHeartbeat, DeviceResult, DisplayDocument, FRAME_BYTES, ImageLayer, NewAdminPassword, RenderOptions, SendRequest, SetupResult
from .admin import AdminAccess, SESSION_SECONDS, set_password
from .device_setup import DeviceSetup
from .preview_service import PreviewService, RenderingBusy
from .storage import DisplayReadCooling, JobStore
from .password_routes import register_password_routes

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD = 10 * 1024 * 1024


def create_app(data_dir: Path | None = None):
    app = FastAPI(title="三色墨水屏工作台", version="1.0.0")
    store = JobStore((data_dir or Path(os.environ.get("EPAPER_DATA_DIR", ROOT / "data"))) / "display.sqlite3")
    previews = PreviewService()
    setup = DeviceSetup()
    admin = AdminAccess(store.path.parent)
    recovery = AdminAccess(store.path.parent, "recovery")
    app.state.store = store
    app.state.previews = previews
    app.state.setup = setup
    app.state.admin = admin
    app.state.recovery = recovery

    def require_recovery(request: Request):
        if not recovery.authorized(request.cookies.get("epaper_recovery", "")):
            raise HTTPException(401, "请先验证超级管理员身份。")

    @app.get("/api/recovery/status")
    def recovery_status(request: Request):
        return {"configured": recovery.configured(), "authenticated": recovery.authorized(request.cookies.get("epaper_recovery", ""))}

    @app.post("/api/recovery/login")
    def recovery_login(credentials: AdminLogin, request: Request, response: FastResponse):
        if not recovery.configured():
            raise HTTPException(503, "请在电脑本机网页的管理设置中初始化超级管理员恢复口令。")
        try:
            token = recovery.login(credentials.password)
        except PermissionError as error:
            raise HTTPException(401, str(error)) from error
        response.set_cookie("epaper_recovery", token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=SESSION_SECONDS, path="/api/recovery")
        return {"ok": True}

    @app.post("/api/recovery/reset-admin", dependencies=[Depends(require_recovery)])
    def reset_admin(credentials: NewAdminPassword):
        set_password(store.path.parent, credentials.new_password)
        return {"ok": True}

    @app.post("/api/recovery/logout")
    def recovery_logout(request: Request, response: FastResponse):
        recovery.logout(request.cookies.get("epaper_recovery", ""))
        response.delete_cookie("epaper_recovery", path="/api/recovery")
        return {"ok": True}

    def require_admin(request: Request):
        if not admin.configured():
            raise HTTPException(503, "请在电脑本机网页的管理设置中初始化管理员密码。")
        if not admin.authorized(request.cookies.get("epaper_admin", "")):
            raise HTTPException(401, "请先输入配网管理员密码。")

    register_password_routes(app, admin, recovery, require_admin)

    @app.get("/api/admin/status")
    def admin_status(request: Request):
        return {"configured": admin.configured(), "authenticated": admin.authorized(request.cookies.get("epaper_admin", ""))}

    @app.post("/api/admin/login")
    def admin_login(credentials: AdminLogin, request: Request, response: FastResponse):
        if not admin.configured():
            raise HTTPException(503, "管理员尚未设置配网管理密码。")
        try:
            token = admin.login(credentials.password)
        except PermissionError as error:
            raise HTTPException(401, str(error)) from error
        response.set_cookie("epaper_admin", token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=SESSION_SECONDS, path="/api")
        return {"ok": True}

    @app.post("/api/admin/logout")
    def admin_logout(request: Request, response: FastResponse):
        admin.logout(request.cookies.get("epaper_admin", ""))
        response.delete_cookie("epaper_admin", path="/api")
        return {"ok": True}

    @app.exception_handler(RenderingBusy)
    def busy_error(request, error):
        return JSONResponse(status_code=429, content={"detail": str(error)})

    @app.exception_handler(LookupError)
    def cache_error(request, error):
        return JSONResponse(status_code=410, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    def image_error(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.post("/api/render")
    def render(file: UploadFile = File(...), options: str = Form("{}", max_length=2048)):
        try:
            settings = RenderOptions.model_validate_json(options)
        except ValidationError as error:
            raise HTTPException(422, "图片处理参数不合法。") from error
        data = _read_upload(file)
        with previews.processing():
            return previews.legacy(data, settings)

    @app.post("/api/images")
    def upload_image(file: UploadFile = File(...)):
        data = _read_upload(file)
        with previews.processing():
            return previews.upload(data)

    @app.get("/api/images/{image_id}/source")
    def source_image(image_id: str):
        asset = previews.asset(image_id)
        return Response(asset.data, media_type=asset.mime, headers={"Cache-Control": "no-store"})

    @app.post("/api/images/{image_id}/render")
    def render_cached_image(image_id: str, options: RenderOptions):
        document = DisplayDocument(session_id=image_id, image=ImageLayer(image_id=image_id, options=options))
        with previews.processing():
            return previews.document(document)

    @app.post("/api/documents/render")
    def compose(document: DisplayDocument):
        with previews.processing():
            return previews.document(document)

    @app.post("/api/display-jobs", status_code=201)
    def send(request: SendRequest):
        if setup.status()["state"] in {"pending", "ready"}:
            raise HTTPException(409, "设备正在配网，请完成配网后发送。")
        result = previews.preview(request.preview_id)
        try:
            return {"job_id": store.create(result.frame, result.png)}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/api/status")
    def status():
        return {**store.status(), "network_setup": setup.status()}

    @app.get("/api/display/current")
    def current_display():
        try:
            snapshot = store.current_display()
        except DisplayReadCooling as error:
            raise HTTPException(429, str(error), headers={"Retry-After": str(error.seconds)}) from error
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        snapshot["png"] = "data:image/png;base64," + base64.b64encode(snapshot["png"]).decode("ascii")
        return JSONResponse(snapshot, headers={"Cache-Control": "no-store"})

    @app.get("/api/device/setup", dependencies=[Depends(require_admin)])
    def setup_status():
        return setup.status(True)

    @app.post("/api/device/setup", status_code=202, dependencies=[Depends(require_admin)])
    def request_setup():
        state = store.status()
        if not state["online"]:
            raise HTTPException(409, "设备未连接，无法下发配网指令。")
        if state["job"] and state["job"]["status"] in {"queued", "downloading", "refreshing"}:
            raise HTTPException(409, "请等待当前屏幕任务完成后重新配网。")
        try:
            return setup.request()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/api/device/setup/{command_id}/result")
    def setup_result(command_id: int, result: SetupResult):
        try:
            setup.complete(command_id, result.url, result.token, result.error)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @app.get("/api/connection")
    def connection(request: Request):
        return JSONResponse(_connection_info(request), headers={"Cache-Control": "no-store"})

    @app.post("/api/device/poll")
    def poll(heartbeat: DeviceHeartbeat | None = None):
        heartbeat = heartbeat or DeviceHeartbeat()
        setup.observe(heartbeat.setup_supported, heartbeat.setup_url)
        job_id = store.poll()
        command = setup.command()
        if command:
            return command
        if job_id is None:
            return Response(status_code=204)
        frame = store.frame(job_id)
        return {"job_id": job_id, "frame_url": f"/api/device/jobs/{job_id}/frame",
                "size": FRAME_BYTES, "crc32": binascii.crc32(frame)}

    @app.get("/api/device/jobs/{job_id}/frame")
    def frame(job_id: int):
        data = store.frame(job_id)
        if data is None:
            raise HTTPException(404, "任务不存在。")
        return Response(data, media_type="application/octet-stream")

    @app.post("/api/device/jobs/{job_id}/result")
    def result(job_id: int, request: DeviceResult):
        try:
            store.result(job_id, request.status, request.error)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    dist = ROOT / "web" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (dist / "index.html").is_file():
            raise HTTPException(503, "请先在 web 目录执行 npm run build。")
        return FileResponse(dist / "index.html")

    return app


def _connection_info(request: Request):
    """当前可访问的入口优先；每次重新枚举网卡，不存储部署者的固定地址。"""
    preferred = "" if request.url.hostname in {"localhost", "127.0.0.1", "::1"} else str(request.base_url).rstrip("/")
    message = ""
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                            if not item[4][0].startswith(("127.", "169.254."))})
    except OSError:
        addresses = []
        message = "无法读取其他网卡地址，请使用当前可访问的工作台地址或查看电脑网络设置。"
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    urls = [f"{request.url.scheme}://{address}:{port}" for address in addresses]
    if preferred:
        urls = [preferred, *[url for url in urls if url != preferred]]
    return {"preferred_url": preferred, "urls": urls, "message": message}


def _read_upload(file):
    try:
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "图片不能超过 10 MB。")
        return data
    finally:
        file.file.close()
