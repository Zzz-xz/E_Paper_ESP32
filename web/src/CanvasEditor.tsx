import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { inks, type Box, type DisplayDocument, type Preview, type ImageLayer, type ImageAsset } from "./api";
import { fitBox, zoomImage } from "./geometry";
import { InlineTextEditor } from "./InlineTextEditor";
import { LoadingSurface } from "./LoadingSurface";
import { Icon } from "./Icon";
import { ImageViewport } from "./ImageViewport";
import { useImagePan } from "./useImagePan";

type Point = { x: number; y: number };
type Props = {
  document: DisplayDocument;
  asset: ImageAsset | null;
  preview: Preview | null;
  renderedDocument: DisplayDocument | null;
  selected: string | null;
  picking: boolean;
  select: (id: string | null) => void;
  changeBox: (id: string, box: Box) => void;
  pickerMove: (point: Point, cursor: Point) => void;
  pickerConfirm: (point: Point, cursor: Point) => void;
  pickerLeave: () => void;
  pickerExit: () => void;
  changeImage: (update: (layer: ImageLayer) => ImageLayer) => void;
  interact: (active: boolean) => void;
  changeText: (id: string, text: string) => void;
  changeTextSize: (id: string, delta: number) => void;
  loading: boolean;
  loadingLabel: string;
  loadError: (message: string) => void;
};

export function ScreenFrame({ children }: { children: ReactNode }) {
  return <div className="screen-frame">{children}</div>;
}

export function CanvasEditor(props: Props) {
  const canvas = useRef<SVGSVGElement>(null);
  const [editing, setEditing] = useState<{ id: string; original: string } | null>(null);
  const [loadedImage, setLoadedImage] = useState("");
  const [failedImage, setFailedImage] = useState("");
  const drag = useRef<{
    id: string;
    start: Point;
    box: Box;
    resize: boolean;
    pan: boolean;
  } | null>(null);
  const { document, preview, selected, picking } = props;
  const shownImage = props.renderedDocument?.image;
  const pan = useImagePan(props.changeImage, props.interact, shownImage ?? null);
  const liveImage = pan.view && document.image?.image_id === pan.view.layer.image_id &&
    (pan.view.active || shownImage?.offset_x !== pan.view.layer.offset_x || shownImage?.offset_y !== pan.view.layer.offset_y)
    ? pan.view.layer : null;
  const edited = document.texts.find((text) => text.id === editing?.id);
  const imageTile = document.image?.image_id === props.renderedDocument?.image?.image_id
    ? preview?.editor_layers.find((layer) => layer.id === "image")?.png : undefined;
  const decoding = !!imageTile && imageTile !== loadedImage && imageTile !== failedImage;
  useEffect(() => {
    const element = canvas.current!;
    const wheel = (event: WheelEvent) => {
      if (selected !== "image" || !document.image || picking || editing || !(event.target as Element).closest('[data-layer="image"]')) return;
      event.preventDefault();
      const bounds = element.getBoundingClientRect();
      const anchor = { x: (event.clientX - bounds.left) * 400 / bounds.width, y: (event.clientY - bounds.top) * 300 / bounds.height };
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? bounds.height : 1);
      props.changeImage((layer) => zoomImage(layer, layer.zoom * Math.exp(-Math.max(-200, Math.min(200, delta)) * 0.002), anchor));
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [selected, document.image, picking, editing, props.changeImage]);
  const layers = [
    ...(document.image ? [{ id: "image", box: document.image.box }] : []),
    ...document.texts.map((text) => ({ id: text.id, box: text.box })),
  ];

  function point(event: { currentTarget: SVGSVGElement; clientX: number; clientY: number }) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) * 400) / bounds.width,
      y: ((event.clientY - bounds.top) * 300) / bounds.height,
    };
  }

  function down(event: PointerEvent<SVGSVGElement>) {
    if (editing) return;
    if (event.button !== 0) return;
    if (picking) {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      props.pickerMove(point(event), { x: event.clientX, y: event.clientY });
      return;
    }
    const target = (event.target as Element).closest<SVGElement>(
      "[data-layer]",
    );
    const id = target?.dataset.layer ?? null;
    props.select(id);
    if (!id) return;
    const layer = layers.find((item) => item.id === id)!;
    const start = point(event);
    const resize = target?.dataset.resize === "true";
    const border = Math.min(start.x - layer.box.x, layer.box.x + layer.box.width - start.x,
                            start.y - layer.box.y, layer.box.y + layer.box.height - start.y) <= 6;
    drag.current = {
      id,
      start,
      box: layer.box,
      resize,
      pan: id === "image" && document.image!.zoom > 1 && !resize && !border && !event.shiftKey,
    };
    if (drag.current.pan) pan.begin(document.image!);
    event.currentTarget.focus();
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent<SVGSVGElement>) {
    const current = point(event);
    if (picking) {
      props.pickerMove(current, { x: event.clientX, y: event.clientY });
      return;
    }
    const active = drag.current;
    if (!active) return;
    const dx = current.x - active.start.x,
      dy = current.y - active.start.y;
    if (active.pan) {
      pan.move({ x: dx, y: dy });
      return;
    }
    const box = active.resize
      ? {
          ...active.box,
          width: Math.max(
            16,
            Math.min(400 - active.box.x, active.box.width + dx),
          ),
          height: Math.max(
            16,
            Math.min(300 - active.box.y, active.box.height + dy),
          ),
        }
      : { ...active.box, x: active.box.x + dx, y: active.box.y + dy };
    props.changeBox(active.id, fitBox(box));
  }

  function up(event: PointerEvent<SVGSVGElement>) {
    if (picking && event.currentTarget.hasPointerCapture(event.pointerId))
      props.pickerConfirm(point(event), { x: event.clientX, y: event.clientY });
    if (drag.current?.pan) {
      const current = point(event);
      pan.move({ x: current.x - drag.current.start.x, y: current.y - drag.current.start.y });
      pan.end();
    }
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <ScreenFrame>
      <svg
        ref={canvas}
        viewBox="0 0 400 300"
        className={"editing-canvas " + (picking ? "picking" : "")}
        aria-label="图文编辑画布"
        role="img"
        tabIndex={0}
        aria-keyshortcuts="Control+ArrowUp Control+ArrowDown"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onContextMenu={(event) => {
          if (picking) { event.preventDefault(); props.pickerExit(); }
        }}
        onDoubleClick={(event) => {
          if (picking) return;
          const position = point(event);
          const id = [...layers].reverse().find(({ box }) => position.x >= box.x && position.x <= box.x + box.width && position.y >= box.y && position.y <= box.y + box.height)?.id;
          const text = document.texts.find((item) => item.id === id);
          if (text) { drag.current = null; props.select(text.id); setEditing({ id: text.id, original: text.text }); }
        }}
        onPointerCancel={() => {
          if (drag.current?.pan) pan.end();
          drag.current = null;
          props.pickerLeave();
        }}
        onPointerLeave={() => {
          if (!drag.current) props.pickerLeave();
        }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          const selectedText = document.texts.find((item) => item.id === selected);
          const larger = event.key === "+" || event.key === "=" || (event.ctrlKey && event.key === "ArrowUp");
          const smaller = event.key === "-" || event.key === "_" || (event.ctrlKey && event.key === "ArrowDown");
          if (selectedText && (larger || smaller)) {
            event.preventDefault();
            props.changeTextSize(selectedText.id, larger ? 1 : -1);
            return;
          }
          const layer = layers.find((item) => item.id === selected);
          const delta = event.shiftKey ? 10 : 1;
          const directions: Record<string, [number, number]> = {
            ArrowLeft: [-delta, 0],
            ArrowRight: [delta, 0],
            ArrowUp: [0, -delta],
            ArrowDown: [0, delta],
          };
          if (layer && directions[event.key]) {
            event.preventDefault();
            const [x, y] = directions[event.key];
            props.changeBox(
              layer.id,
              fitBox({ ...layer.box, x: layer.box.x + x, y: layer.box.y + y }),
            );
          }
        }}
      >
        <rect width="400" height="300" fill={inks[document.background]} />
        {layers.map((layer) => {
          const available =
            layer.id !== "image" ||
            document.image?.image_id ===
              props.renderedDocument?.image?.image_id;
          const tile = available
            ? preview?.editor_layers.find((item) => item.id === layer.id)
            : undefined;
          return (
            <g key={layer.id} data-layer={layer.id}>
              {tile ? (
                <image
                  href={tile.png}
                  onLoad={() => { if (layer.id === "image") setLoadedImage(tile.png); }}
                  onError={() => { if (layer.id === "image") { setFailedImage(tile.png); props.loadError("图片图层加载失败，请重试预览。"); } }}
                  {...layer.box}
                  preserveAspectRatio="none"
                  style={{
                    imageRendering:
                      layer.id === "image" &&
                      document.image?.options.resample === "smooth"
                        ? "auto"
                        : "pixelated",
                  }}
                />
              ) : (
                <>
                  <rect {...layer.box} fill="#f5f6f8" />
                  <text x={layer.box.x + 4} y={layer.box.y + 20} fontSize="14">
                    {layer.id === "image" ? "图片处理中…" : "文字处理中…"}
                  </text>
                </>
              )}
              {layer.id === "image" && props.asset && document.image &&
                <ImageViewport asset={props.asset} layer={liveImage ?? document.image} background={document.background}
                  active={!!liveImage} error={props.loadError} />}
              <rect
                {...layer.box}
                fill="transparent"
                data-layer={layer.id}
                className="layer-hitbox"
              />
            </g>
          );
        })}
        {!picking &&
          layers
            .filter((layer) => layer.id === selected)
            .map((layer) => (
              <g key={layer.id}>
                <rect
                  {...layer.box}
                  fill="none"
                  className="layer-selection"
                  vectorEffect="non-scaling-stroke"
                  pointerEvents="none"
                />
                <rect
                  x={layer.box.x + layer.box.width - 8}
                  y={layer.box.y + layer.box.height - 8}
                  width="8"
                  height="8"
                  className="layer-selection-handle"
                  pointerEvents="none"
                />
                <rect
                  data-layer={layer.id}
                  data-resize="true"
                  x={layer.box.x + Math.max(0, layer.box.width - 32)}
                  y={layer.box.y + Math.max(0, layer.box.height - 32)}
                  width={Math.min(32, layer.box.width)}
                  height={Math.min(32, layer.box.height)}
                  fill="transparent"
                  className="resize-handle"
                />
              </g>
            ))}
      </svg>
      {layers.length === 0 && <div className="canvas-empty"><Icon name="image" /><strong>添加图片或文字</strong><span>开始自由排版</span></div>}
      {pan.view?.active && <span className="pan-feedback">本地取景 · 三色预览同步更新</span>}
      {edited && editing && <InlineTextEditor layer={edited} foreground={document.foreground} background={document.background}
        changeSize={(delta) => props.changeTextSize(edited.id, delta)}
        change={(text) => props.changeText(edited.id, text)} finish={() => setEditing(null)}
        cancel={() => { props.changeText(edited.id, editing.original); setEditing(null); }} />}
      {!editing && !picking && (props.loading || decoding) && <LoadingSurface compact={!!preview} label={props.loading ? props.loadingLabel : "正在载入图片"} />}
    </ScreenFrame>
  );
}
