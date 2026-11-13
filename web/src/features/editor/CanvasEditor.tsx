import { ScreenFrame } from "../../components/ui/ScreenFrame";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { inks, type Box, type DisplayDocument, type Preview, type ImageLayer, type ImageAsset } from "../../lib/api";
import { fitBox, zoomImage } from "./geometry";
import { InlineTextEditor } from "./InlineTextEditor";
import { LoadingSurface } from "../../components/ui/LoadingSurface";
import { Icon } from "../../components/ui/Icon";
import { ImageViewport } from "./ImageViewport";
import { useImagePan } from "./useImagePan";

type Point = { x: number; y: number };
type Props = {
  document: DisplayDocument;
  assets: Record<string, ImageAsset>;
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
  changeImage: (update: (layer: ImageLayer) => ImageLayer, id: string) => void;
  interact: (active: boolean) => void;
  changeText: (id: string, text: string) => void;
  changeTextSize: (id: string, delta: number) => void;
  loading: boolean;
  loadingLabel: string;
  loadError: (message: string) => void;
};

export function CanvasEditor(props: Props) {
  const canvas = useRef<SVGSVGElement>(null);
  const [editing, setEditing] = useState<{ id: string; original: string } | null>(null);
  const [loadedImages, setLoadedImages] = useState<Record<string, string>>({});
  const [failedImages, setFailedImages] = useState<Record<string, string>>({});
  const drag = useRef<{
    id: string;
    start: Point;
    box: Box;
    resize: boolean;
    pan: boolean;
  } | null>(null);
  const { document, preview, selected, picking } = props;
  const imageIds = document.images.map((image) => image.id).join(",");
  useEffect(() => {
    const retained = new Set(document.images.map((image) => image.id));
    setLoadedImages((value) => Object.fromEntries(Object.entries(value).filter(([id]) => retained.has(id))));
    setFailedImages((value) => Object.fromEntries(Object.entries(value).filter(([id]) => retained.has(id))));
  }, [imageIds]);
  const selectedImage = document.images.find((image) => image.id === selected);
  const pan = useImagePan(props.changeImage, props.interact, props.renderedDocument?.images ?? []);
  const shownImage = props.renderedDocument?.images.find((image) => image.id === pan.view?.layer.id);
  const currentPanImage = document.images.find((image) => image.id === pan.view?.layer.id);
  const liveImage = pan.view && currentPanImage?.image_id === pan.view.layer.image_id &&
    (pan.view.active || shownImage?.offset_x !== pan.view.layer.offset_x || shownImage?.offset_y !== pan.view.layer.offset_y)
    ? pan.view.layer : null;
  const edited = document.texts.find((text) => text.id === editing?.id);
  const decoding = document.images.some((image) => {
    const png = preview?.editor_layers.find((layer) => layer.id === image.id)?.png;
    return !!png && png !== loadedImages[image.id] && png !== failedImages[image.id];
  });
  useEffect(() => {
    const element = canvas.current!;
    const wheel = (event: WheelEvent) => {
      if (!selectedImage || picking || editing || (event.target as Element).closest("[data-layer]")?.getAttribute("data-layer") !== selectedImage.id) return;
      event.preventDefault();
      const bounds = element.getBoundingClientRect();
      const anchor = { x: (event.clientX - bounds.left) * 400 / bounds.width, y: (event.clientY - bounds.top) * 300 / bounds.height };
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? bounds.height : 1);
      props.changeImage((layer) => zoomImage(layer, layer.zoom * Math.exp(-Math.max(-200, Math.min(200, delta)) * 0.002), anchor), selectedImage.id);
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [selectedImage, picking, editing, props.changeImage]);
  const layers = [
    ...document.images.map((image) => ({ id: image.id, box: image.box })),
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
    const image = document.images.find((item) => item.id === id);
    const start = point(event);
    const resize = target?.dataset.resize === "true";
    const border = Math.min(start.x - layer.box.x, layer.box.x + layer.box.width - start.x,
                            start.y - layer.box.y, layer.box.y + layer.box.height - start.y) <= 6;
    drag.current = {
      id,
      start,
      box: layer.box,
      resize,
      pan: !!image && image.zoom > 1 && !resize && !border && !event.shiftKey,
    };
    if (drag.current.pan) pan.begin(image!);
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
          const image = document.images.find((item) => item.id === layer.id);
          const asset = image ? props.assets[image.image_id] : undefined;
          const available = !image || image.image_id === props.renderedDocument?.images.find((item) => item.id === layer.id)?.image_id;
          const tile = available
            ? preview?.editor_layers.find((item) => item.id === layer.id)
            : undefined;
          return (
            <g key={layer.id} data-layer={layer.id}>
              {tile ? (
                <image
                  href={tile.png}
                  onLoad={() => { if (image) setLoadedImages((value) => ({ ...value, [image.id]: tile.png })); }}
                  onError={() => { if (image) { setFailedImages((value) => ({ ...value, [image.id]: tile.png })); props.loadError("图片图层加载失败，请重试预览。"); } }}
                  {...layer.box}
                  preserveAspectRatio="none"
                  style={{
                    imageRendering:
                      image?.options.resample === "smooth"
                        ? "auto"
                        : "pixelated",
                  }}
                />
              ) : (
                <>
                  <rect {...layer.box} fill="#f5f6f8" />
                  <text x={layer.box.x + 4} y={layer.box.y + 20} fontSize="14">
                    {image ? "图片处理中…" : "文字处理中…"}
                  </text>
                </>
              )}
              {image && asset && (selected === image.id || liveImage?.id === image.id) &&
                <ImageViewport asset={asset} layer={liveImage?.id === image.id ? liveImage : image} background={document.background}
                  active={liveImage?.id === image.id} error={props.loadError} />}
              <rect
                {...layer.box}
                fill="transparent"
                data-layer={layer.id}
                className="layer-hitbox"
              />
              {!picking && layer.id === selected && <>
                <rect {...layer.box} fill="none" className="layer-selection" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                <rect x={layer.box.x + layer.box.width - 8} y={layer.box.y + layer.box.height - 8} width="8" height="8"
                  className="layer-selection-handle" pointerEvents="none" />
                <rect data-layer={layer.id} data-resize="true"
                  x={layer.box.x + Math.max(0, layer.box.width - 32)} y={layer.box.y + Math.max(0, layer.box.height - 32)}
                  width={Math.min(32, layer.box.width)} height={Math.min(32, layer.box.height)} fill="transparent" className="resize-handle" />
              </>}
            </g>
          );
        })}
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
