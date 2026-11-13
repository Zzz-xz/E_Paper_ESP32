import { useEffect, useState } from "react";
import { request, type Status } from "../../lib/api";

export function useDeviceStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    let alive = true;
    const update = async () => {
      try {
        const next = await request<Status>("/api/status");
        if (alive) setStatus(next);
      } catch {
        if (alive) setStatus(null);
      }
    };
    update();
    const timer = window.setInterval(update, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return { status, setStatus };
}
