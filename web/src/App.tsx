import { Button } from "./Button";
import { useEffect, useRef, useState } from "react";
import { request, type Box, type Status, type ImageLayer, type Ink } from "./api";
import { CanvasEditor, ScreenFrame } from "./CanvasEditor";
import { useColorPicker } from "./ColorPicker";
import { ConnectionGuide, Dialog } from "./dialogs";
import { addText, boxesOverlap, fitBox, resizeBox } from "./geometry";
import { Inspector } from "./Inspector";
import { useComposer } from "./useComposer";
import { useDeviceStatus } from "./useDeviceStatus";
import { Icon } from "./Icon";
import { LoadingSurface } from "./LoadingSurface";
import { SecuritySettings } from "./SecuritySettings";
import { CurrentDisplayViewer } from "./CurrentDisplayViewer";
import { ShortcutGuide } from "./ShortcutGuide";

const states: Record<string, string> = {
  queued: "已接收",
  downloading: "下载中",
  refreshing: "屏幕刷新中",
  completed: "刷新流程完成",
  failed: "显示失败",
};

export function App() {
  const composer = useComposer();
  const { document, preview, asset } = composer;
  const { status, setStatus } = useDeviceStatus();
  const [selected, setSelected] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [guide, setGuide] = useState(false);
  const [security, setSecurity] = useState(false);
  const [shortcuts, setShortcuts] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [decodedPreview, setDecodedPreview] = useState("");
  const [failedPreview, setFailedPreview] = useState("");
  const [zoom, setZoom] = useState<"editor" | "preview" | null>(null);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [aspectLocked, setAspectLocked] = useState(true);
  const lockedRatio = useRef(4 / 3);
  const input = useRef<HTMLInputElement>(null);
  const picker = useColorPicker(
    document.image,
    asset,
    (hue) => {
      composer.change((value) => ({
        ...value,
        image: value.image && {
          ...value.image,
          recommendation: "manual",
          options: {
            ...value.image.options,
            accent_mode: "manual",
            accent_hue: hue,
          },
        },
      }));
      setPicking(false);
    },
    composer.setError,
  );

  useEffect(() => {
    if (document.image) {
      setSelected("image");
      lockedRatio.current = document.image.box.width / document.image.box.height;
    }
    setPicking(false);
  }, [document.image?.image_id]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPicking(false);
        picker.clear();
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  });

  function changeBox(id: string, box: Box) {
    if (id !== "image" && document.image && boxesOverlap(fitBox(box), document.image.box)) {
      composer.setError("文字不能占用图片显示区域，请放置在空白处。");
      return;
    }
    composer.change((value) =>
      id === "image"
        ? { ...value, image: value.image && { ...value.image, box: resizeBox(value.image.box, box, aspectLocked ? lockedRatio.current : null) } }
        : {
            ...value,
            texts: value.texts.map((text) =>
              text.id === id ? { ...text, box: fitBox(box), auto_size: true } : text,
            ),
          },
    );
  }
  function changeImage(update: (layer: ImageLayer) => ImageLayer) {
    composer.change((value) => ({ ...value, image: value.image && update(value.image) }));
  }
  function changeText(id: string, text: string) {
    composer.change((value) => ({ ...value, texts: value.texts.map((item) => item.id === id ? { ...item, text, auto_size: true } : item) }));
  }
  function changeTextSize(id: string, delta: number) {
    composer.change((value) => ({ ...value, texts: value.texts.map((item) => item.id === id
      ? { ...item, auto_size: true, font_size: Math.max(8, Math.min(72, item.font_size + delta)) } : item) }));
  }
  function insertText() {
    const result = addText(document);
    if (!result) {
      composer.setError(
        "空白区域不足或文字已达 12 段。请手动调整图片框留出位置；添加文字不会改变已有图片。",
      );
      return;
    }
    composer.change(() => result.document);
    setSelected(result.id);
    setPicking(false);
    picker.clear();
  }
  function remove() {
    composer.change((value) =>
      selected === "image"
        ? { ...value, image: null }
        : {
            ...value,
            texts: value.texts.filter((text) => text.id !== selected),
          },
    );
    setSelected(null);
    setPicking(false);
    picker.clear();
  }
  function select(id: string | null) {
    setSelected(id);
    setPicking(false);
    picker.clear();
  }
  async function send() {
    if (!preview) return;
    setSending(true);
    setNotice("");
    composer.setError("");
    try {
      await request("/api/display-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_id: preview.preview_id }),
      });
      setNotice("已发送，正在等待设备刷新。");
      setStatus(await request<Status>("/api/status"));
    } catch (failure) {
      composer.setError((failure as Error).message);
    } finally {
      setSending(false);
    }
  }

  const active =
    !!status?.job &&
    ["queued", "downloading", "refreshing"].includes(status.job.status);
  const cooldown = status?.cooldown_seconds ?? 0;
  const configuring = ["pending", "ready"].includes(
    status?.network_setup?.state ?? "idle",
  );
  const hasContent =
    !!document.image || document.texts.some((text) => text.text.trim());
  const previewLoading = composer.updating || (!!preview && preview.png !== decodedPreview && preview.png !== failedPreview);
  const canSend =
    !!preview &&
    preview.png === decodedPreview &&
    !composer.stale &&
    !composer.updating &&
    !interacting &&
    !!status?.online &&
    !active &&
    !cooldown &&
    !sending &&
    !configuring &&
    hasContent;
  const editorProps = {
    document,
    asset,
    preview,
    renderedDocument: composer.renderedDocument,
    selected,
    picking,
    select,
    changeBox,
    pickerMove: picker.move,
    pickerConfirm: picker.confirm,
    pickerLeave: picker.clear,
    pickerExit: () => { setPicking(false); picker.clear(); },
    changeImage,
    interact: setInteracting,
    changeText,
    changeTextSize,
    loading: composer.updating && (hasContent || composer.uploading),
    loadingLabel: composer.uploading ? "正在读取图片" : "正在更新排版",
    loadError: composer.setError,
  };

  return (
    <div className="app-shell">
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            三色墨水屏<small>图文工作台</small>
          </span>
        </div>
        <div className="header-actions">
          <span className={"device-state " + (status?.online ? "online" : "")}>
            <b />
            {status === null
              ? "服务未连接"
              : status.online
                ? "设备已连接"
                : "设备未连接"}
          </span>
          <Button className="text-button" onClick={() => setGuide(true)}>
            <Icon name="wifi" />连接设备
          </Button>
          <Button className="text-button" onClick={() => setSecurity(true)}><Icon name="shield" />管理设置</Button>
          <Button className="text-button" onClick={() => setShortcuts(true)}><Icon name="keyboard" />快捷键说明</Button>
        </div>
      </header>
      <main>
        <div className="intro">
          <div>
            <span className="workspace-eyebrow">E-PAPER STUDIO</span>
            <h1>把喜欢的图文，留在屏幕上。</h1>
            <p>添加内容、自由排版，实时预览黑白红效果。</p>
          </div>
          <div className="screen-spec">
            <span>4.2 寸</span>
            <strong>400 × 300</strong>
            <small>黑白红三色 / 4:3</small>
          </div>
        </div>
        <div className="workspace composer-workspace">
          <div className="images-column">
            <div className="editor-toolbar">
              <Button onClick={() => input.current?.click()}>
                <Icon name="image" />
                {document.image ? "更换图片" : "添加图片"}
              </Button>
              <Button onClick={insertText}><Icon name="text" />＋ 添加文字</Button>
              <div className="canvas-palette" role="group" aria-label="画布配色">
                {(["foreground", "background"] as const).map((role) => <label key={role}>
                  {role === "foreground" ? "前景" : "背景"}
                  <select aria-label={role === "foreground" ? "前景色" : "背景色"} value={document[role]}
                    onChange={(event) => composer.change((value) => ({ ...value, [role]: event.target.value as Ink }))}>
                    {(["black", "white", "red"] as const).map((ink, index) => <option key={ink} value={ink}
                      disabled={document[role === "foreground" ? "background" : "foreground"] === ink}>{["黑色", "白色", "红色"][index]}</option>)}
                  </select>
                </label>)}
                <Button title="交换前景与背景，图片保留原本明暗" onClick={() => composer.change((value) => ({ ...value, foreground: value.background, background: value.foreground }))}><Icon name="swap" />交换</Button>
              </div>
            </div>
            <div className="image-pair">
              <section className="image-panel" aria-busy={composer.updating}>
                <div className="panel-heading">
                  <h2><span className="panel-number">01</span>编辑排版</h2>
                  <Button
                    className="text-button"
                    onClick={() => setZoom("editor")}
                  >
                    <Icon name="expand" />放大编辑
                  </Button>
                </div>
                <div className="canvas-stage">
                  <CanvasEditor {...editorProps} />
                </div>
                <div className="image-caption">
                  <span>
                    {picking
                      ? "点击取色 · 右键退出"
                      : selected === "image" && (document.image?.zoom ?? 1) > 1
                        ? "拖动图片取景 · 拖边框移动"
                        : "拖动排版 · 双击文字"}
                  </span>
                  <span>400 × 300</span>
                </div>
              </section>
              <section className="image-panel preview-panel" aria-busy={previewLoading}>
                <div className="panel-heading">
                  <h2><span className="panel-number">02</span>实屏预览</h2>
                  <Button
                    className="text-button"
                    disabled={!preview}
                    onClick={() => setZoom("preview")}
                  >
                    <Icon name="expand" />放大查看
                  </Button>
                </div>
                <div
                  className={
                    "canvas-stage " + (composer.stale ? "preview-updating" : "")
                  }
                >
                  <ScreenFrame>
                    {preview ? (
                      <img src={preview.png} alt="400×300 黑白红三色预览"
                        onLoad={() => setDecodedPreview(preview.png)}
                        onError={() => { setFailedPreview(preview.png); composer.setError("预览图片加载失败，请重试预览。"); }} />
                    ) : (
                      <div className="preview-empty">
                        <span className="ink-dots">
                          <i />
                          <i />
                          <i />
                        </span>
                        <strong>添加内容后自动预览</strong>
                      </div>
                    )}
                    {previewLoading && <LoadingSurface compact={!!preview} label={composer.uploading ? "正在读取原图" : "正在生成三色预览"} />}
                  </ScreenFrame>
                  {composer.updating && (
                    <span className="updating-badge" role="status">
                      正在更新…
                    </span>
                  )}
                </div>
                <div className="image-caption">
                  <span>边框内即实际显示区域</span>
                  <span>4:3</span>
                </div>
              </section>
            </div>
            <div className="palette-summary">
              <div className="palette-title">三色占比</div>
              {(["black", "white", "red"] as const).map((color, index) => (
                <div className="color-stat" key={color}>
                  <i className={color} />
                  <span>{["黑色", "白色", "红色"][index]}</span>
                  <strong>
                    {preview
                      ? `${(preview.counts[color] / 1200).toFixed(1)}%`
                      : "—"}
                  </strong>
                </div>
              ))}
            </div>
            <p className="quiet-note">
              预览对应最终位面；实屏色调受环境光影响。
            </p>
            {preview?.warnings.map((warning) => (
              <p className="composition-warning" key={warning}>
                {warning}
              </p>
            ))}
            {status?.job && (
              <div
                className={
                  "job-note " +
                  (status.job.status === "failed" ? "job-error" : "")
                }
                role="status"
              >
                <span className="job-light" />
                <strong>{states[status.job.status]}</strong>
                <span>
                  {status.job.error ||
                    (status.job.status === "completed"
                      ? "屏幕已休眠，可查看实际画面。"
                      : "设备正在处理图文画面。")}
                </span>
              </div>
            )}
          </div>
          <Inspector
            recommend={composer.recommend}
            document={document}
            asset={asset}
            selected={selected}
            picking={picking}
            select={select}
            change={composer.change}
            changeBox={changeBox}
            changeImage={changeImage}
            aspectLocked={aspectLocked}
            toggleAspect={() => {
              if (document.image) lockedRatio.current = document.image.box.width / document.image.box.height;
              setAspectLocked(!aspectLocked);
            }}
            remove={remove}
            togglePicker={() => {
              setPicking(!picking);
              picker.clear();
            }}
          />
        </div>
        <div className="action-bar">
          <div>
            {composer.error ? (
              <p className="error" role="alert">
                {composer.error}
              </p>
            ) : (
              <p role="status">
                {composer.updating
                  ? "自动生成预览中，可继续编辑。"
                  : notice ||
                    (cooldown
                      ? `冷却 ${cooldown} 秒，期间可继续编辑。`
                      : hasContent
                        ? "预览已更新，确认后发送到屏幕。"
                        : "添加图片或文字，即可开始。")}
              </p>
            )}
          </div>
          <div className="action-buttons">
            <CurrentDisplayViewer />
            {composer.error && (
              <Button onClick={composer.retry}>重试预览</Button>
            )}
            <Button className="primary" disabled={!canSend} onClick={send}>
              <Icon name="send" />
              {sending
                ? "发送中…"
                : configuring
                  ? "设备配网中"
                  : active
                    ? "设备处理中"
                    : cooldown
                      ? `冷却 ${cooldown}s`
                      : "发送到屏幕"}
            </Button>
          </div>
        </div>
      </main>
      <footer>
        <span>图文自由排，三色留在屏幕上。</span>
        <span>局域网图文工作台</span>
      </footer>
      <input
        hidden
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        aria-label="上传图片"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            setNotice("");
            setPicking(false);
            composer.upload(file);
          }
          event.target.value = "";
        }}
      />
      {guide && (
        <ConnectionGuide close={() => setGuide(false)} status={status} managePasswords={() => { setGuide(false); setSecurity(true); }} />
      )}
      {security && <SecuritySettings close={() => setSecurity(false)} />}
      {shortcuts && <ShortcutGuide close={() => setShortcuts(false)} />}
      {zoom && (
        <Dialog
          title={zoom === "editor" ? "放大编辑" : "三色像素预览"}
          close={() => {
            setZoom(null);
            picker.clear();
          }}
        >
          <div className="large-canvas">
            {zoom === "editor" ? (
              <CanvasEditor {...editorProps} />
            ) : (
              <ScreenFrame>
                {preview && <img src={preview.png} alt="放大的三色像素预览" />}
                {previewLoading && <LoadingSurface compact={!!preview} label="正在生成三色预览" />}
              </ScreenFrame>
            )}
          </div>
          <p>
            {zoom === "editor"
              ? "放大的图片可在框内拖动取景，拖边框或 Shift 拖动可移动图片框；双击文字编辑，Ctrl+↑ / ↓ 调整字号。"
              : "边框内为完整的 400×300 最终像素。"}
          </p>
        </Dialog>
      )}
      {picker.loupe}
    </div>
  );
}
