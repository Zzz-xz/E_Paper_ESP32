import {
  createId,
  type Box,
  type DisplayDocument,
  type ImageAsset,
  type TextLayer,
  type ImageLayer,
} from "../../lib/api";

export const fullScreen: Box = { x: 0, y: 0, width: 400, height: 300 };

export function fitBox(box: Box): Box {
  const width = Math.round(Math.max(1, Math.min(400, box.width)));
  const height = Math.round(Math.max(1, Math.min(300, box.height)));
  return {
    x: Math.round(Math.max(0, Math.min(400 - width, box.x))),
    y: Math.round(Math.max(0, Math.min(300 - height, box.y))),
    width,
    height,
  };
}

function overlaps(a: Box, b: Box) {
  return (
    a.x < b.x + b.width + 8 &&
    a.x + a.width + 8 > b.x &&
    a.y < b.y + b.height + 8 &&
    a.y + a.height + 8 > b.y
  );
}

function blankBox(occupied: Box[], sizes: [number, number][]): Box | null {
  for (const [width, height] of sizes) {
    for (let y = 8; y + height <= 292; y += 8) {
      for (let x = 8; x + width <= 392; x += 8) {
        const box = { x, y, width, height };
        if (!occupied.some((item) => overlaps(item, box))) return box;
      }
    }
  }
  return null;
}

/** 优先放在留白区，空间不足时置于图片上方，已有图片保持用户设置。 */
export function addText(
  document: DisplayDocument,
): { document: DisplayDocument; id: string } | null {
  if (document.texts.length === 12) return null;
  const occupied = document.texts.map((text) => text.box);
  const sizes: [number, number][] = [[184, 40], [120, 32]];
  const box = blankBox([...occupied, ...document.images.map((image) => image.box)], sizes) ?? blankBox(occupied, [
    [184, 40],
    [120, 32],
  ]);
  if (!box) return null;
  const text: TextLayer = {
    id: createId(),
    text: "新建文字",
    box,
    font_size: 24,
    color: "foreground",
    align: "left",
    vertical_align: "top",
    auto_size: true,
  };
  return {
    document: { ...document, texts: [...document.texts, text] },
    id: text.id,
  };
}

export function placeImage(
  document: DisplayDocument,
  asset: ImageAsset,
  id: string,
): DisplayDocument {
  const existing = document.images.find((image) => image.id === id);
  if (existing) return { ...document, images: document.images.map((image) => image.id === id
    ? { ...image, image_id: asset.image_id, recommendation: "manual" } : image) };
  const index = document.images.length;
  const box = index === 0 && document.texts.length === 0 ? fullScreen
    : blankBox([...document.images, ...document.texts].map((layer) => layer.box), [[160, 120], [120, 90], [80, 60]])
      ?? { x: 16 + (index % 4) * 20, y: 16 + Math.floor(index / 4) * 20, width: 160, height: 120 };
  return { ...document, images: [...document.images, {
      id,
      zoom: 1,
      offset_x: 0,
      offset_y: 0,
      recommendation: "manual",
      image_id: asset.image_id,
      box,
      options: asset.recommended_options,
    }] };
}

/** 将屏幕上的图片坐标逆变换到方向修正后的原图，留白区不参与取色。 */
export function sourcePoint(
  point: { x: number; y: number },
  layer: ImageLayer,
  asset: ImageAsset,
) {
  const rotation = layer.options.rotation;
  const width = rotation % 180 ? asset.height : asset.width;
  const height = rotation % 180 ? asset.width : asset.height;
  const ratio =
    layer.options.fit === "contain"
      ? Math.min(layer.box.width / width, layer.box.height / height)
      : Math.max(layer.box.width / width, layer.box.height / height);
  const scale = ratio * layer.zoom;
  const x =
    (point.x - layer.box.x - (layer.box.width - width * scale) / 2 - layer.offset_x * layer.box.width) / scale;
  const y =
    (point.y - layer.box.y - (layer.box.height - height * scale) / 2 - layer.offset_y * layer.box.height) / scale;
  if (x < 0 || y < 0 || x >= width || y >= height) return null;
  const pixelX = Math.floor(x), pixelY = Math.floor(y);
  const original =
    rotation === 90
      ? { x: pixelY, y: asset.height - 1 - pixelX }
      : rotation === 180
        ? { x: asset.width - 1 - pixelX, y: asset.height - 1 - pixelY }
        : rotation === 270
          ? { x: asset.width - 1 - pixelY, y: pixelX }
          : { x: pixelX, y: pixelY };
  return {
    x: Math.max(0, Math.min(asset.width - 1, Math.floor(original.x))),
    y: Math.max(0, Math.min(asset.height - 1, Math.floor(original.y))),
  };
}

/** 锁定框比例时只取一个缩放因子，位置与边界约束在同一处处理。 */
export function resizeBox(box: Box, requested: Box, ratio: number | null): Box {
  if (!ratio || (requested.width === box.width && requested.height === box.height)) return fitBox(requested);
  const useWidth = requested.width !== box.width;
  let width = useWidth ? requested.width : requested.height * ratio;
  const maxWidth = Math.min(400 - box.x, (300 - box.y) * ratio);
  width = Math.min(maxWidth, Math.max(Math.min(maxWidth, Math.max(16, 16 * ratio)), width));
  return fitBox({ ...requested, width, height: width / ratio });
}

export type ObjectAlignment = "left" | "center" | "right" | "top" | "middle" | "bottom";
export function alignBox(box: Box, alignment: ObjectAlignment): Box {
  const x = alignment === "left" ? 0 : alignment === "center" ? (400 - box.width) / 2 : alignment === "right" ? 400 - box.width : box.x;
  const y = alignment === "top" ? 0 : alignment === "middle" ? (300 - box.height) / 2 : alignment === "bottom" ? 300 - box.height : box.y;
  return fitBox({ ...box, x, y });
}

/** 指针处源像素保持不动；偏移用图片框尺寸归一化，与后端采样定义一致。 */
export function zoomImage(layer: ImageLayer, zoom: number, point = { x: layer.box.x + layer.box.width / 2, y: layer.box.y + layer.box.height / 2 }): ImageLayer {
  const next = Math.max(0.25, Math.min(4, zoom));
  const factor = next / layer.zoom;
  const anchorX = (point.x - layer.box.x) / layer.box.width - 0.5;
  const anchorY = (point.y - layer.box.y) / layer.box.height - 0.5;
  return { ...layer, zoom: next,
    offset_x: Math.max(-3, Math.min(3, anchorX - (anchorX - layer.offset_x) * factor)),
    offset_y: Math.max(-3, Math.min(3, anchorY - (anchorY - layer.offset_y) * factor)) };
}

/** 位移沿图片框归一化，与后端采样偏移一致；拖动不会改变框或缩放参数。 */
export function panImage(layer: ImageLayer, start: { x: number; y: number }, delta: { x: number; y: number }): ImageLayer {
  return { ...layer,
    offset_x: Math.max(-3, Math.min(3, start.x + delta.x / layer.box.width)),
    offset_y: Math.max(-3, Math.min(3, start.y + delta.y / layer.box.height)) };
}

export function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

/** 与后端顺时针旋转、等比缩放及归一化偏移保持相同的坐标定义。 */
export function imageTransform(layer: ImageLayer, asset: ImageAsset): string {
  const rotation = layer.options.rotation;
  const width = rotation % 180 ? asset.height : asset.width;
  const height = rotation % 180 ? asset.width : asset.height;
  const ratio = (layer.options.fit === "contain"
    ? Math.min(layer.box.width / width, layer.box.height / height)
    : Math.max(layer.box.width / width, layer.box.height / height)) * layer.zoom;
  const left = (layer.box.width - width * ratio) / 2 + layer.offset_x * layer.box.width;
  const top = (layer.box.height - height * ratio) / 2 + layer.offset_y * layer.box.height;
  const turn = rotation === 90 ? `translate(${asset.height} 0) rotate(90)`
    : rotation === 180 ? `translate(${asset.width} ${asset.height}) rotate(180)`
      : rotation === 270 ? `translate(0 ${asset.width}) rotate(270)` : "";
  return `translate(${left} ${top}) scale(${ratio}) ${turn}`;
}
