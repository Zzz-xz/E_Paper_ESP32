"""原图与最新预览仅保存在有界内存缓存中，SQLite 只接收已确认的最终帧。"""
import base64
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass

from PIL import Image

from .composition import INKS, RenderedDocument, render_document, render_image_tile
from .models import DisplayDocument, ImageLayer, RenderOptions
from .optimization import recommend_options
from .rendering import decode_cached_image, decode_image, prepare_image, render_image

CACHE_SECONDS = 1800


class RenderingBusy(Exception):
    pass


@dataclass(frozen=True)
class ImageAsset:
    data: bytes
    mime: str


class PreviewService:
    def __init__(self):
        self._images = OrderedDict()
        self._previews = OrderedDict()
        self._cache_lock = threading.Lock()
        self._render_lock = threading.Lock()
        self._recommendations = OrderedDict()
        self._decoded = None
        self._tile = None
        self._tile_key = None
        self._prepared = None
        self._prepared_key = None
        self._layers = OrderedDict()

    @contextmanager
    def processing(self):
        if not self._render_lock.acquire(blocking=False):
            raise RenderingBusy("正在处理另一份预览，请稍后重试。")
        try:
            yield
        finally:
            self._render_lock.release()

    def upload(self, data):
        image = decode_image(data)
        options = recommend_options(image)
        image_id = uuid.uuid4().hex
        asset = ImageAsset(data, Image.MIME[image.info["source_format"]])
        with self._cache_lock:
            self._images[image_id] = (time.monotonic(), asset)
            while len(self._images) > 16:
                self._images.popitem(last=False)
        document = DisplayDocument(session_id=image_id, image=ImageLayer(image_id=image_id, options=options))
        self._decoded = (image_id, image)
        self._recommendations[self._recommendation_key(document)] = options
        while len(self._recommendations) > 8:
            self._recommendations.popitem(last=False)
        result = self._render(document, image)
        return {"image_id": image_id, "width": image.width, "height": image.height,
                "recommended_options": options.model_dump(), "preview": self._remember(image_id, result)}

    def document(self, document):
        if document.images:
            return self._document_layers(document)
        image = self._source(document.image.image_id) if document.image else None
        if document.image and document.image.recommendation == "auto":
            layer = document.image
            key = self._recommendation_key(document)
            if key not in self._recommendations:
                self._recommendations[key] = recommend_options(image, layer.options, (layer.box.width, layer.box.height),
                                                               INKS[document.background], layer.zoom,
                                                               (layer.offset_x, layer.offset_y))
                while len(self._recommendations) > 8:
                    self._recommendations.popitem(last=False)
            document = document.model_copy(update={"image": layer.model_copy(update={"options": self._recommendations[key]})})
        return self._remember(document.session_id, self._render(document, image))

    def _document_layers(self, document):
        """各图片独立推荐和缓存；调整一张图片不会重算其他图层。"""
        layers, tiles = [], {}
        for layer in document.images:
            self.asset(layer.image_id)
            if layer.recommendation == "auto":
                key = self._recommendation_key(document, layer)
                if key not in self._recommendations:
                    self._recommendations[key] = recommend_options(self._source(layer.image_id), layer.options,
                        (layer.box.width, layer.box.height), INKS[document.background], layer.zoom,
                        (layer.offset_x, layer.offset_y))
                    while len(self._recommendations) > 8:
                        self._recommendations.popitem(last=False)
                layer = layer.model_copy(update={"options": self._recommendations[key]})
            layers.append(layer)
            tiles[layer.id] = self._layer_tile(document, layer)
        fitted = document.model_copy(update={"images": layers})
        return self._remember(document.session_id, render_document(fitted, None, image_tiles=tiles))

    def _layer_tile(self, document, layer):
        geometry = (layer.image_id, layer.box.width, layer.box.height, layer.zoom, layer.offset_x,
                    layer.offset_y, document.background, layer.options.fit, layer.options.rotation, layer.options.resample)
        key = (*geometry, *layer.options.model_dump().values())
        cached = self._layers.get(layer.id)
        if cached is None or cached[0] != key:
            if cached is not None and cached[1] == geometry:
                prepared = cached[2]
            else:
                prepared = prepare_image(self._source(layer.image_id), layer.options,
                    (layer.box.width, layer.box.height), INKS[document.background], layer.zoom,
                    (layer.offset_x, layer.offset_y))
            tile = render_image_tile(None, layer, INKS[document.background], prepared)
            self._layers[layer.id] = (key, geometry, prepared, tile)
        self._layers.move_to_end(layer.id)
        while len(self._layers) > 8:
            self._layers.popitem(last=False)
        return self._layers[layer.id][3]

    def _source(self, image_id):
        asset = self.asset(image_id)
        if self._decoded is None or self._decoded[0] != image_id:
            self._decoded = (image_id, decode_cached_image(asset.data))
        return self._decoded[1]

    @staticmethod
    def _recommendation_key(document, layer=None):
        layer = layer or document.image
        return (layer.image_id, layer.box.width, layer.box.height, layer.zoom, layer.offset_x, layer.offset_y,
                document.foreground, document.background, layer.options.fit, layer.options.rotation,
                layer.options.resample, layer.options.dither, layer.options.accent_mode, layer.options.accent_hue)

    def _render(self, document, image):
        """只保留最近一个图片图层；移动元素或改文字无需重新量化整张图片。"""
        tile = None
        if document.image:
            layer = document.image
            key = (layer.image_id, layer.box.width, layer.box.height, layer.zoom, layer.offset_x,
                   layer.offset_y, document.background, *layer.options.model_dump().values())
            if key != self._tile_key:
                geometry = (layer.image_id, layer.box.width, layer.box.height, layer.zoom, layer.offset_x,
                            layer.offset_y, document.background, layer.options.fit, layer.options.rotation,
                            layer.options.resample)
                if geometry != self._prepared_key:
                    self._prepared = prepare_image(image, layer.options, (layer.box.width, layer.box.height),
                                                   INKS[document.background], layer.zoom, (layer.offset_x, layer.offset_y))
                    self._prepared_key = geometry
                self._tile = render_image_tile(image, layer, INKS[document.background], self._prepared)
                self._tile_key = key
            tile = self._tile
        return render_document(document, image, tile)

    def legacy(self, data, options):
        result = RenderedDocument(render_image(data, options), [], [])
        return self._remember(uuid.uuid4().hex, result)

    def asset(self, image_id):
        with self._cache_lock:
            entry = self._images.get(image_id)
            if entry is None or time.monotonic() - entry[0] > CACHE_SECONDS:
                self._images.pop(image_id, None)
                raise LookupError("原图缓存已过期，请重新上传。")
            self._images[image_id] = (time.monotonic(), entry[1])
            self._images.move_to_end(image_id)
            return entry[1]

    def preview(self, preview_id):
        with self._cache_lock:
            for created, identifier, result in self._previews.values():
                if identifier == preview_id and time.monotonic() - created <= CACHE_SECONDS:
                    return result.image
        raise LookupError("预览已过期，请重新生成。")

    def _remember(self, owner, result):
        identifier = uuid.uuid4().hex
        with self._cache_lock:
            self._previews[owner] = (time.monotonic(), identifier, result)
            self._previews.move_to_end(owner)
            while len(self._previews) > 8:
                self._previews.popitem(last=False)
        return {"preview_id": identifier, "width": 400, "height": 300,
                "png": "data:image/png;base64," + base64.b64encode(result.image.png).decode("ascii"),
                "counts": result.image.counts, "accent_hue": result.image.accent_hue,
                "editor_layers": result.editor_layers, "warnings": result.warnings,
                "text_boxes": result.text_boxes,
                "applied_images": result.applied_images,
                "applied_options": result.applied_options.model_dump() if result.applied_options else None}
