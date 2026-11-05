import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { request } from "./api";
import { Button } from "./Button";
import { ScreenFrame } from "./CanvasEditor";
import { Dialog } from "./dialogs";
import { Icon } from "./Icon";
import { LoadingSurface } from "./LoadingSurface";

type Snapshot = { png: string; job_id: number; confirmed_at: number; cooldown_seconds: number };
const READ_COOLDOWN_SECONDS = 5;

/** 单次读取最后确认的画面；弹窗关闭不轮询，也不触发屏幕刷新。 */
export function CurrentDisplayViewer() {
  const [open, setOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [decoded, setDecoded] = useState(false);
  const [error, setError] = useState("");
  const [readAt, setReadAt] = useState(0);
  const [now, setNow] = useState(Date.now);
  const remaining = Math.max(0, Math.ceil((readAt - now) / 1000));

  useEffect(() => {
    if (!readAt) return;
    const timer = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= readAt) window.clearInterval(timer);
    }, 250);
    return () => window.clearInterval(timer);
  }, [readAt]);

  async function view() {
    const current = Date.now();
    setOpen(true); setLoading(true); setDecoded(false); setSnapshot(null); setError("");
    setNow(current); setReadAt(current + READ_COOLDOWN_SECONDS * 1000);
    try {
      const result = await request<Snapshot>("/api/display/current", { cache: "no-store" });
      setSnapshot(result);
      setReadAt(Date.now() + result.cooldown_seconds * 1000);
    } catch (failure) { setError((failure as Error).message); }
    finally { setLoading(false); }
  }

  return <>
    <Button disabled={loading || remaining > 0} onClick={view} className="current-display-button">
      <Icon name="image" />{loading ? "获取画面中…" : remaining ? `查看画面 · ${remaining}s` : "查看屏幕当前画面"}
    </Button>
    {open && createPortal(<Dialog title="屏幕当前画面" close={() => setOpen(false)}>
      <div className="current-display-stage">
        <ScreenFrame>
          {snapshot && !error && <img src={snapshot.png} alt="设备最近确认完成的屏幕画面" onLoad={() => setDecoded(true)} onError={() => setError("当前画面图片加载失败，请关闭后重试。")} />}
          {!error && (loading || (snapshot && !decoded)) && <LoadingSurface label="正在获取屏幕画面" />}
        </ScreenFrame>
      </div>
      {snapshot && <p>最近确认刷新：<time dateTime={new Date(snapshot.confirmed_at * 1000).toISOString()}>{new Date(snapshot.confirmed_at * 1000).toLocaleString()}</time></p>}
      <p>这里显示设备最近确认刷新成功的画面。屏幕没有图像回读功能；离线或正在刷新时，以实屏为准。</p>
      <p>本次仅获取一次画面，关闭后返回编辑。再次获取需间隔 5 秒。</p>
      {error && <p className="error" role="alert">{error}</p>}
    </Dialog>, document.body)}
  </>;
}
