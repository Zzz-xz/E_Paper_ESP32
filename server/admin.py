"""管理口令与短期会话；网页和本机工具共用加盐派生值存储。"""
import getpass
import argparse
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from pydantic import ValidationError
from .models import NewAdminPassword

ITERATIONS = 600_000
SESSION_SECONDS = 600


def set_password(directory: Path, password: str, role="admin"):
    """调用方入口已校验长度；两个管理身份的口令必须独立。"""
    _store_password(directory, password, role, "w")


def initialize_password(directory: Path, password: str, role):
    """首次网页设置使用独占创建，已有管理口令不能经初始化入口覆盖。"""
    _store_password(directory, password, role, "x")


def _store_password(directory, password, role, mode):
    other = directory / ("recovery.json" if role == "admin" else "admin.json")
    if other.is_file() and _matches(password, json.loads(other.read_text(encoding="utf-8"))):
        raise ValueError("普通管理员和超级管理员必须使用不同的密码。")
    salt = secrets.token_hex(16)
    record = {"salt": salt, "iterations": ITERATIONS,
              "digest": hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()}
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{role}.json").open(mode, encoding="utf-8") as target:
        json.dump(record, target)


def _matches(password, record):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(record["salt"]), record["iterations"]).hex()
    return hmac.compare_digest(digest, record["digest"])


class AdminAccess:
    def __init__(self, directory, role="admin"):
        self.path = directory / f"{role}.json"
        self._lock = threading.Lock()
        self._sessions = {}
        self._failures = []

    def configured(self):
        return self.path.is_file()

    def login(self, password):
        now = time.monotonic()
        with self._lock:
            self._failures = [timestamp for timestamp in self._failures if now - timestamp < 60]
            if len(self._failures) >= 5:
                raise PermissionError("尝试次数过多，请 60 秒后重试。")
            record = self._record()
            if not _matches(password, record):
                self._failures.append(now)
                raise PermissionError("管理员密码错误。")
            token = secrets.token_urlsafe(32)
            self._sessions = {key: value for key, value in self._sessions.items() if now < value[0]}
            if len(self._sessions) >= 8:
                del self._sessions[next(iter(self._sessions))]
            self._sessions[token] = (now + SESSION_SECONDS, record["digest"])
            self._failures.clear()
            return token

    def authorized(self, token):
        with self._lock:
            session = self._sessions.get(token)
            return bool(session and time.monotonic() < session[0] and self.configured()
                        and hmac.compare_digest(session[1], self._record()["digest"]))

    def logout(self, token):
        with self._lock:
            self._sessions.pop(token, None)

    def _record(self):
        return json.loads(self.path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="本机设置配网管理或超级管理员恢复口令")
    parser.add_argument("--recovery", action="store_true", help="设置仅用于重置普通管理员密码的超级管理员")
    args = parser.parse_args()
    role = "recovery" if args.recovery else "admin"
    label = "超级管理员恢复" if args.recovery else "配网管理员"
    directory = Path(os.environ.get("EPAPER_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
    if args.recovery and (directory / "recovery.json").is_file():
        raise SystemExit("超级管理员恢复口令已固定，本工具不会覆盖。")
    password = getpass.getpass(f"设置{label}密码（8 至 32 字符）：")
    confirmation = getpass.getpass(f"再次输入{label}密码：")
    if password != confirmation:
        raise SystemExit("两次密码不同，未保存。请重新运行。")
    try:
        value = NewAdminPassword(new_password=password)
        set_password(directory, value.new_password, role)
    except ValidationError as error:
        raise SystemExit("密码长度须为 8 至 32 个字符，未保存。") from error
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"{label}密码已设置。网站无需重启，普通用户显示图文无需登录。")


if __name__ == "__main__":
    main()
