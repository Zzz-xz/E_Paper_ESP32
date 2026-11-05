export type Options = {
  fit: "contain" | "cover";
  rotation: number;
  resample: "smooth" | "pixel";
  brightness: number;
  contrast: number;
  accent_mode: "auto" | "manual" | "grayscale_red";
  accent_hue: number;
  accent_strength: number;
  dither: boolean;
};

/** 局域网 HTTP 页面也可使用 getRandomValues，不依赖安全上下文中的 randomUUID。 */
export function createId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}
export type Preview = {
  preview_id: string;
  png: string;
  counts: { black: number; white: number; red: number };
  accent_hue: number | null;
  editor_layers: { id: string; box: Box; png: string }[];
  warnings: string[];
  applied_options: Options | null;
  text_boxes?: Record<string, Box>;
};
export type Box = { x: number; y: number; width: number; height: number };
export type Ink = "black" | "white" | "red";
export const inks: Record<Ink, string> = { black: "#000000", white: "#ffffff", red: "#dc0000" };
export type ImageLayer = { image_id: string; box: Box; options: Options; zoom: number; offset_x: number; offset_y: number; recommendation: "auto" | "manual" };
export type TextLayer = {
  id: string;
  text: string;
  box: Box;
  font_size: number;
  color: "foreground" | Ink;
  align: "left" | "center" | "right";
  vertical_align: "top" | "middle" | "bottom";
  auto_size?: boolean;
};
export type DisplayDocument = {
  session_id: string;
  image: ImageLayer | null;
  texts: TextLayer[];
  foreground: Ink;
  background: Ink;
};
export type ImageAsset = {
  image_id: string;
  width: number;
  height: number;
  recommended_options: Options;
  preview: Preview;
};
export type Status = {
  online: boolean;
  cooldown_seconds: number;
  job: { id: number; status: string; error: string } | null;
  network_setup?: NetworkSetup;
};
export type NetworkSetup = {
  supported: boolean;
  state: "idle" | "pending" | "ready" | "failed";
  url: string;
  error: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    signal: AbortSignal.timeout(15000),
  });
  const body = await response.json();
  if (!response.ok)
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : "请求失败，请检查服务连接。",
      response.status,
    );
  return body as T;
}

export function uploadImage(file: File) {
  const data = new FormData();
  data.append("file", file);
  return request<ImageAsset>("/api/images", { method: "POST", body: data });
}

export function renderDocument(document: DisplayDocument) {
  return request<Preview>("/api/documents/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(document),
  });
}

/** 共享设备忙时仅有限重试；单页面的串行调度由预览 Hook 负责。 */
export async function previewRequest<T>(
  operation: () => Promise<T>,
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await operation();
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 429 || attempt === 2)
        throw error;
      await new Promise((resolve) =>
        window.setTimeout(resolve, 300 * (attempt + 1)),
      );
    }
  }
}
