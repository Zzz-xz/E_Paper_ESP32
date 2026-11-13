import { useState } from "react";
import type { ImageAsset, ImageLayer, Ink } from "../../lib/api";
import { inks } from "../../lib/api";
import { imageTransform } from "./geometry";

/** 拖动时直接绘制原图取景，固定视口裁剪；最终三色像素仍由后端生成。 */
export function ImageViewport({ asset, layer, background, active, error }: {
  asset: ImageAsset;
  layer: ImageLayer;
  background: Ink;
  active: boolean;
  error: (message: string) => void;
}) {
  const [loaded, setLoaded] = useState("");
  const visible = active && loaded === asset.image_id;
  return <svg {...layer.box} viewBox={`0 0 ${layer.box.width} ${layer.box.height}`}
    className="image-viewport" overflow="hidden" visibility={visible ? "visible" : "hidden"}
    pointerEvents="none" data-live-image={visible ? "true" : "false"}>
    <rect width="100%" height="100%" fill={inks[background]} />
    <g className="image-content" transform={imageTransform(layer, asset)}>
      <image href={`/api/images/${asset.image_id}/source`} width={asset.width} height={asset.height}
        onLoad={() => setLoaded(asset.image_id)}
        onError={() => { setLoaded(""); error("本地取景原图加载失败，请重新上传图片。"); }}
        style={{ imageRendering: layer.options.resample === "pixel" ? "pixelated" : "auto" }} />
    </g>
  </svg>;
}
