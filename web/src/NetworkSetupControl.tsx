import { Button } from "./Button";
import { useEffect, useState } from "react";
import { request, type NetworkSetup, type Status } from "./api";
import { RecoveryControl } from "./RecoveryControl";

type AdminState = { configured: boolean; authenticated: boolean };

export function NetworkSetupControl({ status, managePasswords }: { status: Status | null; managePasswords: () => void }) {
  const [admin, setAdmin] = useState<AdminState | null>(null);
  const [setup, setSetup] = useState<NetworkSetup | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recovering, setRecovering] = useState(false);
  useEffect(() => {
    let active = true;
    const update = async () => {
      try {
        const auth = await request<AdminState>("/api/admin/status");
        if (active) setAdmin(auth);
        if (auth.authenticated) {
          const current = await request<NetworkSetup>("/api/device/setup");
          if (active) setSetup(current);
        } else if (active) setSetup(null);
      } catch (failure) {
        if (active) setError((failure as Error).message);
      }
    };
    update();
    const timer = window.setInterval(update, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function login() {
    setBusy(true);
    setError("");
    try {
      await request("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      setAdmin({ configured: true, authenticated: true });
      setSetup(await request<NetworkSetup>("/api/device/setup"));
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError("");
    try {
      setSetup(
        await request<NetworkSetup>("/api/device/setup", { method: "POST" }),
      );
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await request("/api/admin/logout", { method: "POST" });
      setAdmin({ configured: true, authenticated: false });
      setSetup(null);
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  const active =
    !!status?.job &&
    ["queued", "downloading", "refreshing"].includes(status.job.status);
  return (
    <section className="network-admin" aria-label="管理员重新配网">
      <div className="network-admin-heading"><h2>管理员重新配网</h2><Button className="text-button" onClick={managePasswords}>密码设置</Button></div>
      {!admin ? (
        <p>正在读取管理状态…</p>
      ) : !admin.configured ? (
        <p>
          请在运行网站的电脑上打开本机工作台，进入“管理设置”首次设置独立管理密码。
        </p>
      ) : !admin.authenticated ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            login();
          }}
        >
          <label htmlFor="admin-password">配网管理员密码</label>
          <div className="admin-login-row">
            <input
              id="admin-password"
              type="password"
              required
              minLength={8}
              maxLength={32}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" disabled={busy || password.length < 8}>
              验证管理员
            </Button>
          </div>
          <p>普通用户无需验证即可显示图文。</p>
        </form>
      ) : (
        <>
          <div className="network-actions">
            <Button
              disabled={
                busy ||
                !status?.online ||
                active ||
                !setup?.supported ||
                setup?.state === "pending" ||
                setup?.state === "ready"
              }
              onClick={start}
            >
              {setup?.state === "pending" ? "等待设备开启配网页…" : "重新配网"}
            </Button>
            <Button onClick={logout}>退出管理员</Button>
          </div>
          {!status?.online ? (
            <p>设备离线，恢复联网后才能下发指令。</p>
          ) : !setup?.supported ? (
            <p>设备尚未启用网页配网，请先更新固件。</p>
          ) : active ? (
            <p>请等待当前屏幕任务完成。</p>
          ) : null}
          {setup?.state === "ready" && setup.url && (
            <>
              <p>ESP32 配网页地址（由设备实时回报）：<code className="address">{setup.url.split("#")[0]}</code></p>
              <a
                className="button-link primary"
                href={setup.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                打开 ESP32 配网页
              </a>
              <p>
                授权链接 10 分钟内有效，请勿分享。选择扫描到的
                Wi-Fi，再输入网络密码。
              </p>
            </>
          )}
          {setup?.error && (
            <p className="error" role="alert">
              {setup.error}
            </p>
          )}
        </>
      )}
      <Button
        className="recovery-entry"
        onClick={() => setRecovering(!recovering)}
        aria-expanded={recovering}
      >
        {recovering ? "收起密码恢复" : "忘记管理员密码？"}
      </Button>
      {recovering && <RecoveryControl />}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
