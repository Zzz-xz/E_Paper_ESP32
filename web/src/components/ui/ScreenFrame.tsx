import type { ReactNode } from "react";

/** 公共屏幕容器使编辑器和设备画面使用同一比例，无需功能模块相互依赖。 */
export function ScreenFrame({ children }: { children: ReactNode }) {
  return <div className="screen-frame">{children}</div>;
}
