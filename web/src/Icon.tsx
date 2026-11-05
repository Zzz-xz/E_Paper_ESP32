type Name = "image" | "text" | "settings" | "wifi" | "expand" | "send" | "swap" | "shield" | "close" | "check" | "sparkle" | "rotate-left" | "rotate-right" | "keyboard";

const paths: Record<Name, string> = {
  image: "M4 4h16v16H4z M4 15l5-5 4 4 3-3 4 4 M15 8h.01",
  text: "M4 5h16 M12 5v15 M8 20h8",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z",
  wifi: "M3 8a15 15 0 0 1 18 0 M6 12a10 10 0 0 1 12 0 M9 16a5 5 0 0 1 6 0 M12 20h.01",
  expand: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5",
  send: "M3 11 21 3l-8 18-2-8z M11 13 21 3",
  swap: "M4 8h15l-4-4 M20 16H5l4 4",
  shield: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6",
  close: "M6 6l12 12 M18 6 6 18",
  check: "M5 12l4 4L19 6",
  sparkle: "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  "rotate-left": "M3 10a9 9 0 1 1 2 8 M3 4v6h6",
  "rotate-right": "M21 10a9 9 0 1 0-2 8 M21 4v6h-6",
  keyboard: "M3 6h18v12H3z M6 9h1 M10 9h1 M14 9h1 M18 9h.01 M6 12h1 M10 12h1 M14 12h1 M18 12h.01 M7 15h10",
};

/** 项目自绘的统一描边图标，不依赖远程图标资源。 */
export function Icon({ name }: { name: Name }) {
  return <svg className="ui-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
