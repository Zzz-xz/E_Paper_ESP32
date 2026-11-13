import { useEffect, useState } from "react";
import { request, type Status } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { NetworkSetupControl } from "./NetworkSetupControl";

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
