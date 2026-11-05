import { useEffect, useState } from "react";
import { request } from "./api";
import { Button } from "./Button";
import { Dialog } from "./dialogs";
import { Icon } from "./Icon";
import { RecoveryControl } from "./RecoveryControl";

type State = {
  admin_configured: boolean;
  recovery_configured: boolean;
  initialization_allowed: boolean;
};

async function post(path: string, body: object) {
  return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

/** 管理入口不改变普通用户的图文使用权限；口令提交后立即清空输入。 */
export function SecuritySettings({ close }: { close: () => void }) {
  const [state, setState] = useState<State | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    const [configuration, auth] = await Promise.all([
      request<State>("/api/security/status"),
      request<{ authenticated: boolean }>("/api/admin/status"),
    ]);
    setState(configuration);
    setAuthenticated(auth.authenticated);
  }
  useEffect(() => {
    let active = true;
    Promise.all([request<State>("/api/security/status"), request<{ authenticated: boolean }>("/api/admin/status")])
      .then(([configuration, auth]) => { if (active) { setState(configuration); setAuthenticated(auth.authenticated); } })
      .catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, []);

  async function login() {
    setBusy(true); setError(""); setMessage("");
    try {
      await post("/api/admin/login", { password });
      await refresh();
    } catch (failure) { setError((failure as Error).message); }
    finally { setPassword(""); setBusy(false); }
  }

  async function initialize(role: "admin" | "recovery", value: string) {
    await post(`/api/${role}/initialize`, { new_password: value });
    await refresh();
    setMessage(role === "admin" ? (state?.recovery_configured ? "管理员密码已设置，请使用新密码验证。" : "管理员密码已设置。请继续设置独立的超级管理员恢复口令。") : "固定恢复口令已设置，请妥善保存。普通用户无需登录即可使用工作台。");
  }

  async function change(value: string) {
    await post("/api/admin/password", { new_password: value });
    await refresh();
    setMessage("管理员密码已更新，旧会话已失效。请使用新密码验证管理员身份。");
  }

  async function logout() {
    setError("");
    try { await request("/api/admin/logout", { method: "POST" }); await refresh(); }
    catch (failure) { setError((failure as Error).message); }
  }

  const missing = !!state && (!state.admin_configured || !state.recovery_configured);
  return <Dialog title="管理设置" close={close}>
    <div className="security-settings">
      <div className="security-intro"><span className="section-icon"><Icon name="shield" /></span><div><h3>使用开放，配置有权限</h3><p>普通用户可编辑与发送图文；只有管理员能重新配置设备网络。</p></div></div>
      {!state ? <p role="status">正在读取管理状态…</p> : <>
        {missing && !state.initialization_allowed && <div className="security-notice">首次设置须在运行网站的电脑上打开本机工作台，再进入“管理设置”。不能从手机或局域网地址接管初始口令。</div>}
        <div className="security-grid">
          <section className="security-card" aria-label="管理员密码设置">
            <div className="security-card-title"><Icon name="settings" /><h3>管理员密码</h3><span className="role-badge">网络配置</span></div>
            {!state.admin_configured ? <>
              <p>首次设置管理员密码。设置后，重新配网需要验证此密码。</p>
              <NewPasswordForm prefix="initialize-admin" label="管理员密码" action="设置管理员密码" disabled={!state.initialization_allowed} save={(value) => initialize("admin", value)} />
            </> : !authenticated ? <form className="security-form" onSubmit={(event) => { event.preventDefault(); login(); }}>
              <p>验证后可修改密码，也可返回“连接设备”重新配网。</p>
              <label htmlFor="settings-admin-password">当前管理员密码</label>
              <input id="settings-admin-password" type="password" autoComplete="current-password" minLength={8} maxLength={32} required value={password} onChange={(event) => setPassword(event.target.value)} />
              <Button type="submit" className="primary" disabled={busy || password.length < 8}>{busy ? "验证中…" : "验证管理员"}</Button>
            </form> : <>
              <p className="verified-state"><Icon name="check" />管理员已验证</p>
              <NewPasswordForm prefix="change-admin" label="新的管理员密码" action="更新管理员密码" save={change} />
              <Button className="text-button" onClick={logout}>退出管理员</Button>
            </>}
          </section>
          <section className="security-card" aria-label="超级管理员密码设置">
            <div className="security-card-title"><Icon name="shield" /><h3>超级管理员</h3><span className="role-badge">仅密码恢复</span></div>
            {!state.recovery_configured ? <>
              <p>首次设置独立恢复口令，之后固定不变。它只能重置管理员密码，不能直接重新配网。</p>
              <NewPasswordForm prefix="initialize-recovery" label="超级管理员恢复口令" action="设置固定恢复口令" disabled={!state.initialization_allowed} save={(value) => initialize("recovery", value)} />
            </> : <><p className="fixed-credential"><Icon name="check" />固定恢复口令已设置，网页不提供修改入口。</p><RecoveryControl onReset={() => setAuthenticated(false)} /></>}
          </section>
        </div>
      </>}
      {message && <p className="security-success" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  </Dialog>;
}

function NewPasswordForm({ prefix, label, action, disabled = false, save }: {
  prefix: string; label: string; action: string; disabled?: boolean; save: (value: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true); setError("");
    try { await save(password); }
    catch (failure) { setError((failure as Error).message); }
    finally { setPassword(""); setConfirmation(""); setBusy(false); }
  }
  return <form className="security-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <label htmlFor={`${prefix}-password`}>{label}</label>
    <input id={`${prefix}-password`} type="password" required minLength={8} maxLength={32} autoComplete="new-password" disabled={disabled || busy} value={password} onChange={(event) => setPassword(event.target.value)} />
    <label htmlFor={`${prefix}-confirmation`}>再次输入密码</label>
    <input id={`${prefix}-confirmation`} type="password" required minLength={8} maxLength={32} autoComplete="new-password" disabled={disabled || busy} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
    <p className="control-help">8～32 个字符；两个管理身份的口令必须不同。</p>
    {confirmation && password !== confirmation && <p className="field-error">两次输入不一致</p>}
    <Button type="submit" className="primary" disabled={disabled || busy || password.length < 8 || password !== confirmation}>{busy ? "保存中…" : action}</Button>
    {error && <p className="error" role="alert">{error}</p>}
  </form>;
}
