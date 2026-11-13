import { Button } from "../../components/ui/Button";
import { useEffect, useState } from "react";
import { ApiError, request } from "../../lib/api";

type RecoveryState = { configured: boolean; authenticated: boolean };

export function RecoveryControl({ onReset }: { onReset?: () => void }) {
  const [state, setState] = useState<RecoveryState | null>(null);
  const [password, setPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    request<RecoveryState>("/api/recovery/status")
      .then((value) => {
        if (active) setState(value);
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      });
    return () => {
      active = false;
    };
  }, []);

  async function login() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request("/api/recovery/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      setState({ configured: true, authenticated: true });
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request("/api/recovery/reset-admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: nextPassword }),
      });
      onReset?.();
      await request("/api/recovery/logout", { method: "POST" });
      setState({ configured: true, authenticated: false });
      setMessage(
        "普通管理员密码已重置，旧管理员会话已失效。请返回使用新密码验证。",
      );
    } catch (failure) {
      setError((failure as Error).message);
      if (failure instanceof ApiError && failure.status === 401)
        setState({ configured: true, authenticated: false });
    } finally {
      setNextPassword("");
      setConfirmation("");
      setBusy(false);
    }
  }

  return (
    <section className="recovery-panel" aria-label="超级管理员恢复">
      <h2>超级管理员 · 重置管理密码</h2>
      <p>此身份仅用于重置普通管理员密码，不能直接重新配网。</p>
      {!state ? (
        <p>正在读取恢复状态…</p>
      ) : !state.configured ? (
        <p>
          请在电脑本机网页的“管理设置”中，首次设置本部署固定恢复口令。
        </p>
      ) : !state.authenticated ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            login();
          }}
        >
          <label htmlFor="recovery-password">超级管理员恢复口令</label>
          <div className="admin-login-row">
            <input
              id="recovery-password"
              type="password"
              autoComplete="current-password"
              required
              minLength={8}
              maxLength={32}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" disabled={busy || password.length < 8}>
              验证恢复身份
            </Button>
          </div>
        </form>
      ) : (
        <form
          className="recovery-reset"
          onSubmit={(event) => {
            event.preventDefault();
            reset();
          }}
        >
          <label htmlFor="new-admin-password">新的普通管理员密码</label>
          <input
            id="new-admin-password"
            type="password"
            required
            minLength={8}
            maxLength={32}
            autoComplete="new-password"
            value={nextPassword}
            onChange={(event) => setNextPassword(event.target.value)}
          />
          <label htmlFor="confirm-admin-password">再次输入新密码</label>
          <input
            id="confirm-admin-password"
            type="password"
            required
            minLength={8}
            maxLength={32}
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
          <p>8～32 个字符，两次输入须一致，不能使用超级管理员口令。</p>
          <Button
            type="submit"
            disabled={
              busy || nextPassword.length < 8 || nextPassword !== confirmation
            }
          >
            重置普通管理员密码
          </Button>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
