import { Button } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { useEffect, useState } from "react";
import type {
  Box,
  DisplayDocument,
  ImageAsset,
  Options,
  TextLayer,
  ImageLayer,
} from "../../lib/api";
import { alignBox, zoomImage, type ObjectAlignment } from "./geometry";

type Props = {
  document: DisplayDocument;
  asset: ImageAsset | null;
  selected: string | null;
  picking: boolean;
  select: (id: string | null) => void;
  change: (update: (value: DisplayDocument) => DisplayDocument) => void;
  changeBox: (id: string, box: Box) => void;
  togglePicker: () => void;
  remove: () => void;
  changeImage: (update: (layer: ImageLayer) => ImageLayer) => void;
  aspectLocked: boolean;
  toggleAspect: () => void;
  recommend: () => void;
  replaceImage: () => void;
  uploading: boolean;
};

export function Inspector(props: Props) {
  const [tab, setTab] = useState<"layout" | "color">("layout");
  const { document, selected } = props;
  const text = document.texts.find((item) => item.id === selected);
  const image = document.images.find((item) => item.id === selected);
  const box = image?.box ?? text?.box;
  function changeText(update: Partial<TextLayer>) {
    props.change((value) => ({
      ...value,
      texts: value.texts.map((item) =>
        item.id === selected ? { ...item, ...update, auto_size: true } : item,
      ),
    }));
  }
  function changeOption<K extends keyof Options>(key: K, value: Options[K]) {
    props.changeImage((image) => ({ ...image, recommendation: "manual", options: { ...image.options, [key]: value } }));
  }
  const options = image?.options;
  function rotate(degrees: number) {
    props.changeImage((layer) => ({ ...layer, options: { ...layer.options, rotation: (layer.options.rotation + degrees + 360) % 360 } }));
  }

  return (
    <aside className="controls editor-inspector">
      <div className="inspector-heading">
        <h2>元素属性</h2>
        <span>属性区可滚动</span>
      </div>
      <label className="field-label" htmlFor="selected-layer">
        当前元素
      </label>
      <div className="layer-selector">
      <select
        id="selected-layer"
        value={selected ?? ""}
        onChange={(event) => props.select(event.target.value || null)}
      >
        <option value="">选择图片或文字</option>
        {document.images.map((image, index) => <option key={image.id} value={image.id}>图片 {index + 1}</option>)}
        {document.texts.map((item, index) => (
          <option key={item.id} value={item.id}>
            文字 {index + 1} · {item.text.slice(0, 10) || "空文字"}
          </option>
        ))}
      </select>
      {image && <Button className="replace-image-button" aria-label="更换这张图片" title="更换这张图片，保留当前图层设置" disabled={props.uploading} onClick={props.replaceImage}><Icon name="image" />替换</Button>}
      </div>
      {!box && (
        <p className="inspector-empty">
          最多添加 8 张图片和 12 段文字。文字在图片上方，可自由叠放；选中元素后拖动、缩放或编辑。
        </p>
      )}
      {box && (
        <>
          {image && (
            <>
            <div className="property-tabs segmented">
              <Button aria-pressed={tab === "layout"} className={tab === "layout" ? "selected" : ""} onClick={() => setTab("layout")}>位置与尺寸</Button>
              <Button aria-pressed={tab === "color"} className={tab === "color" ? "selected" : ""} onClick={() => setTab("color")}>图片调色</Button>
            </div>
            {tab === "layout" && <div className="image-orientation">
              <label className="field-label" htmlFor="rotation">图片方向</label>
              <div className="orientation-controls" role="group" aria-label="图片旋转">
                <Button title="逆时针旋转 90°，实时更新预览" onClick={() => rotate(-90)}><Icon name="rotate-left" />左转 90°</Button>
                <select id="rotation" value={options!.rotation} aria-label="图片旋转角度" onChange={(event) => changeOption("rotation", Number(event.target.value))}>
                  {[0, 90, 180, 270].map((value) => <option key={value} value={value}>{value}°</option>)}
                </select>
                <Button title="顺时针旋转 90°，实时更新预览" onClick={() => rotate(90)}><Icon name="rotate-right" />右转 90°</Button>
              </div>
            </div>}
            </>
          )}
          {text && (
            <div className="text-properties">
              <label className="field-label" htmlFor="text-content">
                文字内容 <small>{text.text.length}/500</small>
              </label>
              <textarea
                id="text-content"
                rows={3}
                maxLength={500}
                value={text.text}
                onChange={(event) => changeText({ text: event.target.value })}
              />
              <div className="field-grid">
                <label>
                  字号
                  <FontSizeInput value={text.font_size} change={(font_size) => changeText({ font_size })} />
                </label>
                <label>
                  文字墨色
                  <select
                    id="text-color"
                    value={text.color}
                    onChange={(event) =>
                      changeText({
                        color: event.target.value as TextLayer["color"],
                      })
                    }
                  >
                    <option value="foreground">跟随前景色</option>
                    <option value="black">黑色</option>
                    <option value="red">红色</option>
                    <option value="white">白色</option>
                  </select>
                </label>
              </div>
              <p className="control-help keyboard-help">选中文字后按 + / − 调整字号，Ctrl+↑ / ↓ 在原位编辑时也可使用。文字框随内容自动扩展，可叠在图片上方。</p>
              <div className="alignment-controls">
                <div className="alignment-row">
                  <span>水平</span>
                  <div
                    className="segmented"
                    role="group"
                    aria-label="文字水平对齐"
                  >
                    {(["left", "center", "right"] as const).map(
                      (align, index) => (
                        <Button
                          key={align}
                          className={text.align === align ? "selected" : ""}
                          aria-pressed={text.align === align}
                          onClick={() => changeText({ align })}
                        >
                          {["左对齐", "水平居中", "右对齐"][index]}
                        </Button>
                      ),
                    )}
                  </div>
                </div>
                <div className="alignment-row">
                  <span>垂直</span>
                  <div
                    className="segmented"
                    role="group"
                    aria-label="文字垂直对齐"
                  >
                    {(["top", "middle", "bottom"] as const).map(
                      (vertical_align, index) => (
                        <Button
                          key={vertical_align}
                          className={
                            text.vertical_align === vertical_align
                              ? "selected"
                              : ""
                          }
                          aria-pressed={text.vertical_align === vertical_align}
                          onClick={() => changeText({ vertical_align })}
                        >
                          {["顶端对齐", "垂直居中", "底端对齐"][index]}
                        </Button>
                      ),
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
          {(text || tab === "layout") && (
            <>
              <details className="alignment-disclosure">
                <summary>元素对齐到屏幕</summary>
                <div className="object-alignment-buttons" role="group" aria-label="元素对齐到屏幕">
                  {(["left", "center", "right", "top", "middle", "bottom"] as ObjectAlignment[]).map((alignment, index) =>
                    <Button key={alignment} onClick={() => props.changeBox(selected!, alignBox(box, alignment))}>
                      {["靠左", "水平居中", "靠右", "靠上", "垂直居中", "靠下"][index]}
                    </Button>)}
                </div>
              </details>
              {image && <label className="checkbox aspect-lock"><input id="aspect-lock" type="checkbox" checked={props.aspectLocked} onChange={props.toggleAspect} />锁定图片框比例</label>}
              <div className="geometry-fields" title="位置和尺寸单位为屏幕像素；可拖动元素移动、右下角缩放。">
                {(["x", "y", "width", "height"] as const).map((key, index) => (
                  <label key={key} htmlFor={`box-${key}`}>
                    {["X 位置", "Y 位置", "宽度", "高度"][index]}
                    <input
                      id={`box-${key}`}
                      type="number"
                      min={index < 2 ? 0 : 1}
                      max={key === "x" || key === "width" ? 400 : 300}
                      value={box[key]}
                      onChange={(event) => {
                        const value = Number(event.target.value);
                        if (Number.isFinite(value))
                          props.changeBox(selected!, { ...box, [key]: value });
                      }}
                    />
                  </label>
                ))}
              </div>
            </>
          )}
          {options && tab === "layout" && (
            <>
              <div className="image-zoom-controls">
                <label htmlFor="image-zoom">框内缩放 <output>{Math.round(image!.zoom * 100)}%</output></label>
                <input id="image-zoom" type="range" min="25" max="400" step="5" value={image!.zoom * 100}
                  onChange={(event) => props.changeImage((layer) => zoomImage(layer, Number(event.target.value) / 100))} />
                <Button onClick={() => props.changeImage((layer) => ({ ...layer, zoom: 1, offset_x: 0, offset_y: 0 }))}>恢复 100%</Button>
              </div>
              <p className="control-help" title="放大后按住左键拖动图片取景；拖边框或按住 Shift 拖动可移动图片框。">滚轮缩放 · 左键取景 · Shift 拖框</p>
              <div className="image-fit-controls">
              <label className="field-label">图片填充</label>
              <div className="segmented">
                <Button
                  className={options.fit === "contain" ? "selected" : ""}
                  aria-pressed={options.fit === "contain"}
                  onClick={() => changeOption("fit", "contain")}
                >
                  完整显示
                </Button>
                <Button
                  className={options.fit === "cover" ? "selected" : ""}
                  aria-pressed={options.fit === "cover"}
                  onClick={() => changeOption("fit", "cover")}
                >
                  铺满裁剪
                </Button>
              </div>
              </div>
              <div className="image-resample-controls">
                <label htmlFor="resample">缩放方式</label>
                  <select
                    id="resample"
                    value={options.resample}
                    onChange={(event) =>
                      changeOption(
                        "resample",
                        event.target.value as Options["resample"],
                      )
                    }
                  >
                    <option value="smooth">平滑</option>
                    <option value="pixel">像素画</option>
                  </select>
              </div>
            </>
          )}
          {options && tab === "color" && (
            <div className="image-adjustments">
              <p className="recommendation-status">{image!.recommendation === "auto" ? "正在计算建议参数…" : "当前参数优先 · 修改实时预览"}</p>
              <label className="field-label" htmlFor="accent">
                三色表达
              </label>
              <select
                id="accent"
                value={options.accent_mode}
                onChange={(event) =>
                  changeOption(
                    "accent_mode",
                    event.target.value as Options["accent_mode"],
                  )
                }
              >
                <option value="auto">自动选择重点色</option>
                <option value="manual">自选颜色映射为红色</option>
                <option value="grayscale_red">灰度图红色风格化</option>
              </select>
              <Button
                className={"pick-button " + (props.picking ? "selected" : "")}
                aria-pressed={props.picking}
                onClick={props.togglePicker}
              >
                {props.picking ? "退出取色" : "放大取色 · 选择重点色"}
              </Button>
              {options.accent_mode === "manual" && (
                <Slider
                  label="重点色相"
                  id="hue"
                  value={options.accent_hue}
                  min={0}
                  max={360}
                  step={1}
                  change={(value) => changeOption("accent_hue", value)}
                />
              )}
              <Slider
                label="红色强度"
                id="strength"
                value={options.accent_strength}
                min={0}
                max={1}
                step={0.05}
                change={(value) => changeOption("accent_strength", value)}
              />
              <Slider
                label="亮度"
                id="brightness"
                value={options.brightness}
                min={0.5}
                max={1.5}
                step={0.05}
                change={(value) => changeOption("brightness", value)}
              />
              <Slider
                label="对比度"
                id="contrast"
                value={options.contrast}
                min={0.5}
                max={1.5}
                step={0.05}
                change={(value) => changeOption("contrast", value)}
              />
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={options.dither}
                  onChange={(event) =>
                    changeOption("dither", event.target.checked)
                  }
                />
                网点抖动
              </label>
              <Button
                className="restore-button"
                disabled={!props.asset}
                onClick={props.recommend}
              >
                自动推荐参数
              </Button>
            </div>
          )}
          <Button className="delete-button" disabled={!!image && props.uploading} title={image && props.uploading ? "上传完成后可删除单张图片，也可随时清空所有图片" : undefined} onClick={props.remove}>
            删除{image ? "图片" : "这段文字"}
          </Button>
        </>
      )}
    </aside>
  );
}

function FontSizeInput({ value, change }: { value: number; change: (size: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  return <input id="font-size" type="number" min="8" max="72" value={draft}
    onChange={(event) => {
      setDraft(event.target.value);
      const size = Number(event.target.value);
      if (Number.isInteger(size) && size >= 8 && size <= 72) change(size);
    }}
    onBlur={() => setDraft(String(value))} />;
}

function Slider({
  label,
  id,
  value,
  min,
  max,
  step,
  change,
}: {
  label: string;
  id: string;
  value: number;
  min: number;
  max: number;
  step: number;
  change: (value: number) => void;
}) {
  return (
    <div className="slider-row">
      <label htmlFor={id}>
        {label}
        <output>{id === "hue" ? `${value}°` : value.toFixed(2)}</output>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => change(Number(event.target.value))}
      />
    </div>
  );
}
