"""单设备重新配网指令及回报，仅保存运行时地址，不保存网络口令。"""
import threading
import time


class DeviceSetup:
    def __init__(self):
        self._lock = threading.Lock()
        self._supported = False
        self._state = "idle"
        self._url = ""
        self._token = ""
        self._error = ""
        self._id = 0
        self._created = 0.0

    def observe(self, supported, url):
        with self._lock:
            self._supported = supported
            if url and self._token:
                self._state, self._url, self._error = "ready", url, ""
            elif self._state == "ready":
                self._state, self._url = "idle", ""
                self._token = ""

    def request(self):
        with self._lock:
            if not self._supported:
                raise ValueError("当前固件尚未启用网页配网，请先升级固件。")
            self._expire()
            if self._state not in {"pending", "ready"}:
                self._id = time.time_ns() // 1_000_000
                self._created = time.monotonic()
                self._state, self._url, self._error, self._token = "pending", "", "", ""
            return self._snapshot(True)

    def command(self):
        with self._lock:
            self._expire()
            return {"command": "setup", "command_id": self._id} if self._state == "pending" else None

    def complete(self, identifier, url, token, error):
        with self._lock:
            if identifier != self._id or self._state != "pending":
                raise ValueError("配网指令已过期，请重新发起。")
            self._state = "failed" if error else "ready"
            self._url, self._error = url, error
            self._token = token

    def status(self, authorized=False):
        with self._lock:
            self._expire()
            return self._snapshot(authorized)

    def _expire(self):
        if self._state == "pending" and time.monotonic() - self._created >= 30:
            self._state, self._error = "failed", "设备未响应配网指令，请检查连接后重试。"

    def _snapshot(self, authorized=False):
        url = self._url + "#token=" + self._token if authorized and self._url and self._token else ""
        return {"supported": self._supported, "state": self._state, "url": url, "error": self._error}
