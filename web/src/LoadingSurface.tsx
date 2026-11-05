import { Icon } from "./Icon";

/** 仅由实际上传、渲染或图片解码状态挂载；流光不表示虚构的进度百分比。 */
export function LoadingSurface({ label, compact = false }: { label: string; compact?: boolean }) {
  return <div className={"loading-surface" + (compact ? " loading-compact" : "")} role="status" aria-live="polite">
    <span className="loading-beam" aria-hidden="true" />
    <span className="loading-label"><Icon name="sparkle" />{label}<span className="loading-dots" aria-hidden="true">···</span></span>
  </div>;
}
