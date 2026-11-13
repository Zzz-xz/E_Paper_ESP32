import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { ScalarSpring } from "../../lib/spring";

/** 弹窗统一管理键盘焦点和退出行为，业务页面只提供内容。 */
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
