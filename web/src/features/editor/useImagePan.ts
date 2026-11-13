import { useEffect, useRef, useState } from "react";
import type { ImageLayer } from "../../lib/api";
import { panImage } from "./geometry";

const PREVIEW_INTERVAL_MS = 120;

/** 本地取景按浏览器绘制帧更新，后端仅接收合并后的偏移；结束时提交最终位置。 */
export function useImagePan(change: (update: (layer: ImageLayer) => ImageLayer, id: string) => void, interact: (active: boolean) => void, rendered: ImageLayer[]) {
  const [view, setView] = useState<{ layer: ImageLayer; active: boolean } | null>(null);
  const gesture = useRef<{ origin: ImageLayer; latest: ImageLayer; published: number } | null>(null);
  const animation = useRef(0);

  useEffect(() => {
    const image = rendered.find((item) => item.id === view?.layer.id);
    if (view && !view.active && image?.image_id === view.layer.image_id &&
        image.offset_x === view.layer.offset_x && image.offset_y === view.layer.offset_y) setView(null);
  }, [rendered, view]);

  useEffect(() => () => {
    cancelAnimationFrame(animation.current);
    if (gesture.current) interact(false);
  }, []);

  function publish(layer: ImageLayer) {
    change((current) => ({ ...current, offset_x: layer.offset_x, offset_y: layer.offset_y }), layer.id);
  }

  function begin(layer: ImageLayer) {
    gesture.current = { origin: layer, latest: layer, published: performance.now() };
    setView({ layer, active: true });
    interact(true);
  }

  function move(delta: { x: number; y: number }) {
    const active = gesture.current!;
    active.latest = panImage(active.origin, { x: active.origin.offset_x, y: active.origin.offset_y }, delta);
    if (animation.current) return;
    animation.current = requestAnimationFrame((now) => {
      animation.current = 0;
      setView({ layer: active.latest, active: true });
      if (now - active.published >= PREVIEW_INTERVAL_MS) {
        active.published = now;
        publish(active.latest);
      }
    });
  }

  function end() {
    const active = gesture.current!;
    cancelAnimationFrame(animation.current);
    animation.current = 0;
    gesture.current = null;
    setView({ layer: active.latest, active: false });
    publish(active.latest);
    interact(false);
  }

  return { view, begin, move, end };
}
