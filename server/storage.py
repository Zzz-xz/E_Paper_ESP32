import sqlite3
import threading
import time
from contextlib import contextmanager
from math import ceil
from pathlib import Path

from .models import COOLDOWN_SECONDS, DISPLAY_READ_COOLDOWN_SECONDS

ACTIVE = {"queued", "downloading", "refreshing"}
JOB_TIMEOUTS = {"queued": 15, "downloading": 45, "refreshing": 120}
IDLE_HEARTBEAT_SECONDS = 10


class DisplayReadCooling(Exception):
    def __init__(self, seconds):
        super().__init__(f"请在 {seconds} 秒后再次获取屏幕画面。")
        self.seconds = seconds


class JobStore:
    """保留当前任务和最后确认的屏幕画面；事务保护共享设备的唯一发送入口。"""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.Lock()
        self.last_seen = 0.0
        self._last_display_read = None
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS job (id INTEGER PRIMARY KEY, state TEXT, frame BLOB, png BLOB, created REAL, updated REAL, error TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS displayed (id INTEGER PRIMARY KEY, job_id INTEGER, png BLOB, confirmed REAL)")
            db.execute("INSERT OR IGNORE INTO displayed SELECT 1,id,png,updated FROM job WHERE state='completed'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _expire(self, db, now):
        for state, seconds in JOB_TIMEOUTS.items():
            db.execute("UPDATE job SET state='failed', error=?, updated=? WHERE state=? AND updated<?",
                       ("设备" + {"queued": "接收任务", "downloading": "下载图片", "refreshing": "刷新屏幕"}[state] +
                        "超时，请检查连接后重新发送。", now, state, now - seconds))

    def _cooldown(self, db, now):
        row = db.execute("SELECT value FROM meta WHERE key='cooldown_until'").fetchone()
        return max(0, ceil((row[0] if row else 0) - now))

    def status(self):
        now = time.time()
        with self.lock, self.connect() as db:
            self._expire(db, now)
            row = db.execute("SELECT id,state,created,updated,error FROM job").fetchone()
            heartbeat_seconds = 90 if row and row[1] in {"downloading", "refreshing"} else IDLE_HEARTBEAT_SECONDS
            return {"online": now - self.last_seen < heartbeat_seconds,
                    "last_seen": self.last_seen or None,
                    "cooldown_seconds": self._cooldown(db, now),
                    "job": dict(zip(("id", "status", "created", "updated", "error"), row)) if row else None}

    def create(self, frame: bytes, png: bytes):
        now = time.time()
        with self.lock, self.connect() as db:
            self._expire(db, now)
            row = db.execute("SELECT state FROM job").fetchone()
            if row and row[0] in ACTIVE:
                raise ValueError("屏幕正在处理另一张图片，请等待完成。")
            if now - self.last_seen >= IDLE_HEARTBEAT_SECONDS:
                raise ValueError("设备心跳已中断，请等待重新连接后发送。")
            if self._cooldown(db, now):
                raise ValueError("屏幕正在冷却，请倒计时结束后发送。")
            # 使用毫秒时间作为持久任务编号，固件以 64 位整数处理。
            job_id = time.time_ns() // 1_000_000
            db.execute("DELETE FROM job")
            db.execute("INSERT INTO job VALUES (?,?,?,?,?,?,?)", (job_id, "queued", frame, png, now, now, ""))
            return job_id

    def poll(self):
        now = time.time()
        with self.lock, self.connect() as db:
            self.last_seen = now
            self._expire(db, now)
            row = db.execute("SELECT id,state FROM job").fetchone()
            if not row or row[1] not in {"queued", "downloading"}:
                return None
            if row[1] == "queued":
                db.execute("UPDATE job SET state='downloading', updated=?", (now,))
            return row[0]

    def frame(self, job_id: int):
        with self.connect() as db:
            row = db.execute("SELECT frame FROM job WHERE id=?", (job_id,)).fetchone()
            return row[0] if row else None

    def current_display(self):
        """只读取设备确认完成的位面预览；查看限流与屏幕刷新冷却分别计时。"""
        now = time.monotonic()
        with self.lock, self.connect() as db:
            if self._last_display_read is not None:
                remaining = ceil(self._last_display_read + DISPLAY_READ_COOLDOWN_SECONDS - now)
                if remaining > 0:
                    raise DisplayReadCooling(remaining)
            row = db.execute("SELECT job_id,png,confirmed FROM displayed WHERE id=1").fetchone()
            if not row:
                raise LookupError("尚无设备确认完成的画面，请先发送并完成一次屏幕刷新。")
            self._last_display_read = now
            return {"job_id": row[0], "png": row[1], "confirmed_at": row[2],
                    "cooldown_seconds": DISPLAY_READ_COOLDOWN_SECONDS}

    def result(self, job_id: int, state: str, error: str):
        now = time.time()
        with self.lock, self.connect() as db:
            self._expire(db, now)
            row = db.execute("SELECT state FROM job WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise LookupError("任务不存在。")
            previous = row[0]
            allowed = {"downloading": {"refreshing", "failed"}, "refreshing": {"completed", "failed"}}
            if state != previous and state not in allowed.get(previous, set()):
                raise ValueError("任务状态不匹配。")
            self.last_seen = now
            db.execute("UPDATE job SET state=?, error=?, updated=? WHERE id=?", (state, error, now, job_id))
            if state == "refreshing" and previous != state:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('cooldown_until',?)", (now + COOLDOWN_SECONDS,))
            if state == "completed" and previous != state:
                db.execute("INSERT OR REPLACE INTO displayed SELECT 1,id,png,? FROM job WHERE id=?", (now, job_id))
