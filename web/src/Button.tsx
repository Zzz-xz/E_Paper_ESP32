import { useEffect, useRef, type ButtonHTMLAttributes } from "react";
import { ScalarSpring } from "./spring";

/** 原生按钮保留稳定点击范围，只让内层材质与文字共同压缩。 */
export function Button({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const element = useRef<HTMLButtonElement>(null);
  const spring = useRef<ScalarSpring | null>(null);
  useEffect(() => () => spring.current?.dispose(), []);
  useEffect(() => { if (props.disabled) spring.current?.to(1); }, [props.disabled]);

  function target(value: number) {
    if (!spring.current && value === 1) return;
    if (!spring.current) spring.current = new ScalarSpring(1, (scale) => element.current?.style.setProperty("--press-scale", String(scale)));
    spring.current.to(value);
  }

  return (
    <button {...props} ref={element} className={`ui-button ${className}`}
      onPointerDown={(event) => { if (!props.disabled && event.button === 0) target(0.972); props.onPointerDown?.(event); }}
      onPointerUp={(event) => { target(1); props.onPointerUp?.(event); }}
      onPointerCancel={(event) => { target(1); props.onPointerCancel?.(event); }}
      onPointerLeave={(event) => { target(1); props.onPointerLeave?.(event); }}
      onKeyDown={(event) => { if (!props.disabled && [" ", "Enter"].includes(event.key)) target(0.972); props.onKeyDown?.(event); }}
      onKeyUp={(event) => { target(1); props.onKeyUp?.(event); }}
      onBlur={(event) => { target(1); props.onBlur?.(event); }}>
      <span className="button-content">{children}</span>
    </button>
  );
}
