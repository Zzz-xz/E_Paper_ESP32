import { useEffect, useRef, useState } from "react";
import { ApiError, createId, previewRequest, renderDocument, uploadImage,
  type DisplayDocument, type ImageAsset, type Preview } from "../../lib/api";
import { placeImage } from "./geometry";

type Upload = { file: File; layerId: string; epoch: number; deferPreview?: boolean };

/** 上传与渲染串行执行，每张上传后先更新合成预览；旧结果不能覆盖最新编辑或恢复已清空图片。 */
export function useComposer() {
  const [document, setDocument] = useState<DisplayDocument>(() => ({
    session_id: createId(), images: [], texts: [], foreground: "black", background: "white",
  }));
  const [assets, setAssets] = useState<Record<string, ImageAsset>>({});
  const [lastAdded, setLastAdded] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [renderedDocument, setRenderedDocument] = useState<DisplayDocument | null>(null);
  const [updating, setUpdating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const current = useRef(document);
  const revision = useRef(0), renderedRevision = useRef(0);
  const running = useRef(false), alive = useRef(true);
  const deadline = useRef(0), lastStarted = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const epoch = useRef(0);
  const queue = useRef<Upload[]>([]), activeUpload = useRef<Upload | null>(null);
  const files = useRef(new Map<string, File>());
  const failedUpload = useRef<Upload | null>(null);
  const errorCode = useRef(0);

  useEffect(() => () => { alive.current = false; window.clearTimeout(timer.current); }, []);

  function schedule() {
    window.clearTimeout(timer.current);
    if (!running.current && alive.current)
      timer.current = window.setTimeout(run, Math.max(0, deadline.current - Date.now()));
  }

  function change(update: (value: DisplayDocument) => DisplayDocument, recommend = false) {
    const next = update(current.current);
    current.current = recommend ? next : { ...next, images: next.images.map((image) => ({ ...image, recommendation: "manual" })) };
    const retained = new Set(current.current.images.map((image) => image.id));
    for (const id of files.current.keys()) if (!retained.has(id)) files.current.delete(id);
    setAssets((previous) => Object.fromEntries(Object.entries(previous).filter(([id]) => current.current.images.some((image) => image.image_id === id))));
    setDocument(current.current);
    revision.current++;
    deadline.current = lastStarted.current + 40;
    setStale(true); setUpdating(true); setError(""); schedule();
  }

  function upload(incoming: File[], replaceId?: string) {
    const batch = replaceId ? incoming.slice(0, 1) : incoming;
    if (batch.some((file) => file.size > 10 * 1024 * 1024)) { setError("每张图片不能超过 10 MB。"); return; }
    const occupied = new Set([...current.current.images.map((image) => image.id), ...queue.current.map((job) => job.layerId)]);
    if (activeUpload.current?.epoch === epoch.current) occupied.add(activeUpload.current.layerId);
    if (!replaceId && occupied.size + batch.length > 8) { setError("最多同时放置 8 张图片，请先删除或清空部分图片。"); return; }
    failedUpload.current = null;
    queue.current.push(...batch.map((file) => ({ file, layerId: replaceId ?? createId(), epoch: epoch.current })));
    setUploading(true); setStale(true); setUpdating(true); setError(""); deadline.current = 0; schedule();
  }

  async function run() {
    if (!alive.current || running.current) return;
    running.current = true; lastStarted.current = Date.now();
    const job = renderedRevision.current === revision.current || queue.current[0]?.deferPreview ? queue.current.shift() : undefined;
    activeUpload.current = job ?? null;
    const version = revision.current, snapshot = current.current;
    try {
      if (job) {
        const asset = await previewRequest(() => uploadImage(job.file));
        if (alive.current && job.epoch === epoch.current) {
          const next = placeImage(current.current, asset, job.layerId);
          files.current.set(job.layerId, job.file);
          setAssets((previous) => ({ ...previous, [asset.image_id]: asset }));
          change(() => next);
          setLastAdded(job.layerId);
        }
      } else {
        const result = await previewRequest(() => renderDocument(snapshot));
        const sameImages = snapshot.images.length === current.current.images.length && snapshot.images.every((image, index) =>
          image.id === current.current.images[index].id && image.image_id === current.current.images[index].image_id);
        if (alive.current && sameImages) {
          const applied = { ...snapshot,
            images: snapshot.images.map((image) => ({ ...image, recommendation: "manual" as const, options: result.applied_images[image.id] ?? image.options })),
            texts: snapshot.texts.map((text) => result.text_boxes?.[text.id] ? { ...text, box: result.text_boxes[text.id] } : text),
          };
          setPreview(result); setRenderedDocument(applied);
          if (version === revision.current) { current.current = applied; setDocument(applied); setStale(false); setError(""); }
        }
        renderedRevision.current = version;
      }
    } catch (failure) {
      if (alive.current && (job ? job.epoch === epoch.current : version === revision.current)) {
        setError(failure instanceof Error ? failure.message : "预览失败，请重试。");
        errorCode.current = failure instanceof ApiError ? failure.status : 0;
        failedUpload.current = job ?? null;
        queue.current = [];
        renderedRevision.current = revision.current;
      }
    } finally {
      running.current = false; activeUpload.current = null;
      if (alive.current) {
        setUploading(queue.current.length > 0);
        if (queue.current.length || renderedRevision.current !== revision.current) schedule();
        else setUpdating(false);
      }
    }
  }

  function clearImages() {
    epoch.current++; queue.current = []; failedUpload.current = null; files.current.clear();
    setAssets({}); setUploading(false); setLastAdded("");
    change((value) => ({ ...value, images: [] }));
  }

  function retry() {
    const failed = failedUpload.current;
    if (failed && !failed.deferPreview) {
      queue.current = [{ ...failed, epoch: epoch.current }]; failedUpload.current = null;
      setUploading(true); setUpdating(true); setError(""); schedule();
    } else if (errorCode.current === 410 || failed?.deferPreview) {
      queue.current = current.current.images.map((image) => ({ file: files.current.get(image.id)!, layerId: image.id, epoch: epoch.current, deferPreview: true }));
      setUploading(true); setUpdating(true); setError(""); schedule();
    } else change((value) => ({ ...value }));
  }

  function recommend(id: string) {
    change((value) => ({ ...value, images: value.images.map((image) => image.id === id ? { ...image, recommendation: "auto" } : image) }), true);
  }

  return { document, assets, lastAdded, preview, renderedDocument, updating, uploading, stale, error, setError,
    change, upload, clearImages, retry, recommend };
}
