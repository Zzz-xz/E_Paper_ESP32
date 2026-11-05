import { Button } from "./Button";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { request, type Status } from "./api";
import { NetworkSetupControl } from "./NetworkSetupControl";
import { Icon } from "./Icon";
import { ScalarSpring } from "./spring";

export function Dialog({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const surface = useRef<HTMLElement>(null);
  const onClose = useRef(close);
  onClose.current = close;
  const spring = useRef<ScalarSpring | null>(null);
  const closing = useRef(false);

  function dismiss() {
    if (closing.current) return;
    closing.current = true;
    spring.current!.to(0.97, () => onClose.current());
  }
  useEffect(() => {
    const original = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    spring.current = new ScalarSpring(0.97, (value) => {
      surface.current?.style.setProperty("--dialog-scale", String(value));
      surface.current?.style.setProperty("--dialog-reveal", String(Math.max(0, Math.min(1, (value - 0.97) / 0.03))));
    });
    spring.current.to(1);
    surface.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.key === "Escape") dismiss();
      if (event.key === "Tab") {
        const focusable = [...surface.current!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')].filter((element) => element.getClientRects().length > 0);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener("keydown", escape);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", escape);
      spring.current?.dispose();
      previousFocus?.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop" onPointerDown={(event) => { if (event.target === event.currentTarget) dismiss(); }}>
      <section
        ref={surface}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="panel-heading">
          <h2>{title}</h2>
          <Button onClick={dismiss}><Icon name="close" />关闭</Button>
        </div>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}

export function ConnectionGuide({
  close,
  status,
  managePasswords,
}: {
  close: () => void;
  status: Status | null;
  managePasswords: () => void;
}) {
  const [addresses, setAddresses] = useState<{ preferred_url: string; urls: string[]; message: string } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    request<{ preferred_url: string; urls: string[]; message: string }>("/api/connection", { cache: "no-store" })
      .then((value) => {
        if (active) setAddresses(value);
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refresh]);
  return (
    <Dialog title="连接设备" close={close}>
      <NetworkSetupControl status={status} managePasswords={managePasswords} />
      <ol className="guide-steps">
        <li>电脑保持运行此网站，手机与 ESP32 使用同一局域网。</li>
        <li>
          首次烧录后在串口查看配置热点与配网页；已连接设备可在上方由管理员重新配网。
        </li>
        <li>手机连接该热点，填写 2.4 GHz Wi-Fi 和电脑工作台地址。</li>
        <li>连接成功后切回家庭 Wi-Fi，工作台收到心跳即显示设备已连接。</li>
      </ol>
      <section className="connection-addresses" aria-label="动态工作台地址" aria-busy={loading}>
        <div className="connection-address-heading"><h3>工作台连接地址</h3><Button disabled={loading} onClick={() => setRefresh((value) => value + 1)}>{loading ? "读取中…" : "刷新地址"}</Button></div>
        {addresses?.preferred_url ? <>
          <p>根据本次访问自动生成，可用于手机访问和填写 ESP32 的电脑工作台地址。</p>
          <code className="address preferred-address">{addresses.preferred_url}</code>
          {addresses.urls.some((url) => url !== addresses.preferred_url) && <details className="other-addresses">
            <summary>其他网卡地址（可能包含虚拟网卡）</summary>
            {addresses.urls.filter((url) => url !== addresses.preferred_url).map((url) => <code className="address" key={url}>{url}</code>)}
          </details>}
        </> : <>
          <p>当前使用电脑本机地址，手机不能使用此地址。请选择电脑实际 WLAN 或以太网的地址：</p>
          {addresses?.urls.map((url) => <code className="address" key={url}>{url}</code>)}
        </>}
        <p>地址每次打开或刷新时实时获取，未写死在程序中。同一台电脑的工作台，手机和电脑使用相同局域网地址。</p>
        {addresses?.message && <p role="status">{addresses.message}</p>}
      </section>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p>localhost 仅供本机访问。Wi-Fi 密码只提交给 ESP32。</p>
    </Dialog>
  );
}
