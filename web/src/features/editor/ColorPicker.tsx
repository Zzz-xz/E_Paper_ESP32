import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ImageAsset, ImageLayer } from "../../lib/api";
import { sourcePoint } from "./geometry";

type Point = { x: number; y: number };
type Sample = { cursor: Point; rgb: number[]; x: number; y: number };

export function useColorPicker(
  layer: ImageLayer | null,
  asset: ImageAsset | null,
  confirmHue: (hue: number) => void,
  onError: (message: string) => void,
) {
  const original = useRef<HTMLImageElement | null>(null);
  const working = useRef<HTMLCanvasElement | null>(null);
  const display = useRef<HTMLCanvasElement>(null);
  const animation = useRef(0);
  const pending = useRef<{ point: Point; cursor: Point } | null>(null);
  const [sample, setSample] = useState<Sample | null>(null);

  useEffect(() => {
    original.current = null;
    setSample(null);
    if (!asset) return;
    const image = new Image();
    image.onload = () => {
      original.current = image;
    };
    image.onerror = () => onError("无法读取原图，请重新上传后取色。");
    image.src = `/api/images/${asset.image_id}/source`;
    return () => {
      image.onload = null;
      image.onerror = null;
      original.current = null;
    };
  }, [asset]);
  useEffect(() => () => cancelAnimationFrame(animation.current), []);

  function read(point: Point, cursor: Point): Sample | null {
    if (!layer || !asset || !original.current) return null;
    const position = sourcePoint(point, layer, asset);
    if (!position) return null;
    if (!working.current) {
      working.current = document.createElement("canvas");
      working.current.width = working.current.height = 168;
    }
    const context = working.current.getContext("2d", {
      willReadFrequently: true,
    })!;
    context.fillStyle = "#fff";
    context.fillRect(0, 0, 168, 168);
    context.imageSmoothingEnabled = false;
    context.drawImage(
      original.current,
      position.x - 10,
      position.y - 10,
      21,
      21,
      0,
      0,
      168,
      168,
    );
    return {
      cursor,
      rgb: Array.from(context.getImageData(84, 84, 1, 1).data).slice(0, 3),
      ...position,
    };
  }

  function move(point: Point, cursor: Point) {
    pending.current = { point, cursor };
    if (animation.current) return;
    animation.current = requestAnimationFrame(() => {
      animation.current = 0;
      const next = pending.current!;
      setSample(read(next.point, next.cursor));
    });
  }

  function clear() {
    cancelAnimationFrame(animation.current);
    animation.current = 0;
    setSample(null);
  }

  function confirm(point: Point, cursor: Point) {
    const value = read(point, cursor);
    clear();
    if (value) confirmHue(rgbHue(value.rgb));
  }

  useLayoutEffect(() => {
    if (sample && display.current && working.current)
      display.current.getContext("2d")!.drawImage(working.current, 0, 0);
  }, [sample]);

  const hex = sample
    ? "#" +
      sample.rgb.map((value) => value.toString(16).padStart(2, "0")).join("")
    : "";
  const loupe =
    sample &&
    createPortal(
      <div
        className="color-loupe"
        role="img"
        aria-label={`取色放大镜 ${hex}`}
        style={{
          left: Math.max(
            8,
            Math.min(
              innerWidth - 192,
              sample.cursor.x + 20 > innerWidth - 192
                ? sample.cursor.x - 204
                : sample.cursor.x + 20,
            ),
          ),
          top: Math.max(
            8,
            Math.min(
              innerHeight - 248,
              sample.cursor.y + 20 > innerHeight - 248
                ? sample.cursor.y - 260
                : sample.cursor.y + 20,
            ),
          ),
        }}
      >
        <div className="loupe-image">
          <canvas ref={display} width="168" height="168" />
          <i />
        </div>
        <div className="sample-color">
          <i style={{ background: hex }} />
          <strong>{hex.toUpperCase()}</strong>
          <span>8×</span>
        </div>
        <small>RGB {sample.rgb.join(", ")}</small>
        <small>
          原图像素 {sample.x}, {sample.y} · 点击确认
        </small>
      </div>,
      document.body,
    );
  return { move, confirm, clear, loupe };
}

function rgbHue(rgb: number[]) {
  const [r, g, b] = rgb.map((value) => value / 255);
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b),
    delta = max - min;
  const hue =
    delta === 0
      ? 0
      : max === r
        ? 60 * (((g - b) / delta) % 6)
        : max === g
          ? 60 * ((b - r) / delta + 2)
          : 60 * ((r - g) / delta + 4);
  return Math.round((hue + 360) % 360);
}
