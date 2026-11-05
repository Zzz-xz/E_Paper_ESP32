import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createId,
  previewRequest,
  renderDocument,
  uploadImage,
  type DisplayDocument,
  type ImageAsset,
  type Preview,
} from "./api";
import { placeImage } from "./geometry";

/** 串行处理上传和渲染，只保留最新编辑意图，避免旧帧覆盖新参数。 */
export function useComposer() {
  const [document, setDocument] = useState<DisplayDocument>(() => ({
    session_id: createId(),
    image: null,
    texts: [],
    foreground: "black",
    background: "white",
  }));
  const [asset, setAsset] = useState<ImageAsset | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [renderedDocument, setRenderedDocument] =
    useState<DisplayDocument | null>(null);
  const [updating, setUpdating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const current = useRef(document);
  const revision = useRef(0);
  const renderedRevision = useRef(0);
  const running = useRef(false);
  const alive = useRef(true);
  const deadline = useRef(0);
  const lastStarted = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const uploadToken = useRef(0);
  const pendingUpload = useRef<{
    file: File;
    token: number;
    preserve: boolean;
  } | null>(null);
  const lastFile = useRef<File | null>(null);
  const uploadFailed = useRef(false);
  const errorCode = useRef(0);

  useEffect(
    () => () => {
      alive.current = false;
      window.clearTimeout(timer.current);
    },
    [],
  );

  function schedule() {
    window.clearTimeout(timer.current);
    if (!running.current && alive.current)
      timer.current = window.setTimeout(
        run,
        Math.max(0, deadline.current - Date.now()),
      );
  }

  function change(update: (value: DisplayDocument) => DisplayDocument, recommend = false) {
    const next = update(current.current);
    current.current = next.image && !recommend
      ? { ...next, image: { ...next.image, recommendation: "manual" } } : next;
    setDocument(current.current);
    revision.current++;
    deadline.current = lastStarted.current + 40;
    setStale(true);
    setUpdating(true);
    setError("");
    schedule();
  }

  function upload(file: File, preserve = false) {
    if (file.size > 10 * 1024 * 1024) {
      setError("图片不能超过 10 MB。");
      return;
    }
    lastFile.current = file;
    pendingUpload.current = { file, token: ++uploadToken.current, preserve };
    setUploading(true);
    setStale(true);
    setUpdating(true);
    setError("");
    deadline.current = 0;
    schedule();
  }

  async function run() {
    if (!alive.current || running.current) return;
    running.current = true;
    lastStarted.current = Date.now();
    const job = pendingUpload.current;
    pendingUpload.current = null;
    const version = revision.current;
    const snapshot = current.current;
    try {
      if (job) {
        const nextAsset = await previewRequest(() => uploadImage(job.file));
        if (alive.current && job.token === uploadToken.current) {
          const next = placeImage(current.current, nextAsset, job.preserve);
          setAsset(nextAsset);
          uploadFailed.current = false;
          change(() => next);
        }
      } else {
        const result = await previewRequest(() => renderDocument(snapshot));
        if (
          alive.current &&
          snapshot.image?.image_id === current.current.image?.image_id &&
          !pendingUpload.current
        ) {
          const fitted = { ...snapshot, texts: snapshot.texts.map((text) => result.text_boxes?.[text.id]
            ? { ...text, box: result.text_boxes[text.id] } : text) };
          const applied = fitted.image && result.applied_options
            ? { ...fitted, image: { ...fitted.image, recommendation: "manual" as const, options: result.applied_options } }
            : fitted;
          setPreview(result);
          setRenderedDocument(applied);
          /** 拖动期间显示单调推进的已完成帧，但不能回写旧参数或解除发送限制。 */
          if (version === revision.current) {
            current.current = applied;
            setDocument(applied);
            setStale(false);
            setError("");
          }
        }
        renderedRevision.current = version;
      }
    } catch (failure) {
      if (
        alive.current &&
        (job ? job.token === uploadToken.current : version === revision.current)
      ) {
        setError(
          failure instanceof Error ? failure.message : "预览失败，请重试。",
        );
        errorCode.current = failure instanceof ApiError ? failure.status : 0;
        uploadFailed.current = !!job;
        renderedRevision.current = revision.current;
      }
    } finally {
      running.current = false;
      if (alive.current) {
        if (job && job.token === uploadToken.current && !pendingUpload.current) setUploading(false);
        if (
          pendingUpload.current ||
          renderedRevision.current !== revision.current
        )
          schedule();
        else setUpdating(false);
      }
    }
  }

  function retry() {
    if ((uploadFailed.current || errorCode.current === 410) && lastFile.current)
      upload(lastFile.current, !uploadFailed.current);
    else change((value) => ({ ...value }));
  }

  function recommend() {
    change((value) => ({ ...value, image: value.image && { ...value.image, recommendation: "auto" } }), true);
  }

  return {
    document,
    asset,
    preview,
    renderedDocument,
    updating,
    uploading,
    stale,
    error,
    setError,
    change,
    upload,
    retry,
    recommend,
  };
}
