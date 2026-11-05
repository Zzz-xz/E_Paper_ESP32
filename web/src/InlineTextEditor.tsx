import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { inks, type Ink, type TextLayer } from "./api";

type Props = {
  layer: TextLayer;
  foreground: Ink;
  background: Ink;
  change: (text: string) => void;
  changeSize: (delta: number) => void;
  finish: () => void;
  cancel: () => void;
};

/** 原位输入只负责编辑；预览仍使用后端字体生成最终像素。 */
export function InlineTextEditor(props: Props) {
  const input = useRef<HTMLTextAreaElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  useLayoutEffect(() => {
    const parent = input.current!.parentElement!;
    const observer = new ResizeObserver(() => setScale(parent.clientWidth / 400));
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const { layer } = props;
  return (
    <textarea
      ref={input}
      className="inline-text-editor"
      aria-label="原位编辑文字"
      maxLength={500}
      value={layer.text}
      onChange={(event) => props.change(event.target.value)}
      onBlur={props.finish}
      style={{
        left: `${layer.box.x / 4}%`,
        top: `${layer.box.y / 3}%`,
        width: `${layer.box.width / 4}%`,
        height: `${layer.box.height / 3}%`,
        fontSize: Math.max(12, layer.font_size * scale),
        lineHeight: 1.35,
        textAlign: layer.align,
        color: inks[layer.color === "foreground" ? props.foreground : layer.color],
        background: inks[props.background],
      }}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing) return;
        if (event.ctrlKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
          event.preventDefault();
          props.changeSize(event.key === "ArrowUp" ? 1 : -1);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          props.cancel();
        }
        if (event.key === "Enter" && event.ctrlKey) {
          event.preventDefault();
          props.finish();
        }
      }}
    />
  );
}
