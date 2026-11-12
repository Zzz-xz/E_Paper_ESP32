"""后端统一生成编辑图层与实屏位面，避免浏览器字体排版差异。"""
import base64
import io
from dataclasses import dataclass, field

from PIL import Image

from .models import DisplayDocument, HEIGHT, WIDTH, RenderOptions
from .rendering import RenderedImage, compose_image, compose_prepared, finish_frame, quantize_image
from .text_layout import INKS, fit_text_boxes, text_tile


@dataclass(frozen=True)
class RenderedDocument:
    image: RenderedImage
    editor_layers: list[dict]
    warnings: list[str]
    applied_options: RenderOptions | None = None
    text_boxes: dict = field(default_factory=dict)
    applied_images: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedTile:
    image: Image.Image
    editor_png: str
    hue: float | None


def render_image_tile(image, layer, background, prepared=None):
    tile = (compose_prepared(prepared, layer.options) if prepared else
            compose_image(image, layer.options, (layer.box.width, layer.box.height),
                          background, layer.zoom, (layer.offset_x, layer.offset_y)))
    quantized, hue = quantize_image(tile, layer.options)
    return RenderedTile(quantized, png_url(tile), hue)


def render_document(document: DisplayDocument, image: Image.Image | None, image_tile: RenderedTile | None = None,
                    image_tiles: dict | None = None) -> RenderedDocument:
    document = fit_text_boxes(document)
    background = INKS[document.background]
    canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
    layers, warnings = [], []
    hue = None
    for layer in document.picture_layers:
        tile = image_tiles[layer.id] if image_tiles is not None else image_tile or render_image_tile(image, layer, background)
        hue = tile.hue
        canvas.paste(tile.image, (layer.box.x, layer.box.y))
        layers.append({"id": layer.id, "box": layer.box.model_dump(), "png": tile.editor_png})
    for text in document.texts:
        tile, clipped = text_tile(text, document.foreground)
        canvas.paste(tile, (text.box.x, text.box.y), tile.getchannel("A"))
        layers.append(_editor_layer(text.id, text.box, tile))
        if clipped:
            warnings.append(f"文字「{text.text[:12]}」超出文本框，请增大文本框或减小字号。")
    return RenderedDocument(finish_frame(canvas, hue), layers, warnings,
                            document.image.options if document.image else None,
                            {text.id: text.box.model_dump() for text in document.texts if text.auto_size},
                            {layer.id: layer.options.model_dump() for layer in document.picture_layers})


def png_url(image: Image.Image) -> str:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _editor_layer(identifier, box, image):
    return {"id": identifier, "box": box.model_dump(), "png": png_url(image)}
