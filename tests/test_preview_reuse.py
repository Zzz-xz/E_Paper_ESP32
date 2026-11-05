"""验证实时编辑复用图片计算，但参数或画布变化时必须重新生成正确像素。"""
import io

from PIL import Image

from server import preview_service
from server.composition import render_document
from server.models import DisplayDocument, ImageLayer, RenderOptions, CanvasBox, TextLayer
from server.preview_service import PreviewService
from server.rendering import decode_cached_image


def picture():
    stream = io.BytesIO()
    Image.new("RGB", (80, 60), (220, 100, 40)).save(stream, "PNG")
    return stream.getvalue()


def test_initial_recommendation_is_not_repeated_and_manual_values_are_exact(monkeypatch):
    calls = []
    original = preview_service.recommend_options

    def recommend(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(preview_service, "recommend_options", recommend)
    service = PreviewService()
    source = picture()
    asset = service.upload(source)
    document = DisplayDocument(session_id="editor", image=ImageLayer(image_id=asset["image_id"],
        options=RenderOptions(**asset["recommended_options"]), recommendation="auto"))
    service.document(document)
    assert len(calls) == 1
    document.image.recommendation = "manual"
    document.image.options.brightness = 0.73
    document.image.options.contrast = 1.17
    document.image.options.accent_strength = 0.4
    result = service.document(document)
    assert len(calls) == 1
    assert result["applied_options"] == document.image.options.model_dump()
    assert service.preview(result["preview_id"]).frame == render_document(document, decode_cached_image(source)).image.frame


def test_moving_and_text_edits_reuse_tile_but_color_changes_invalidate_it(monkeypatch):
    calls = []
    original = preview_service.render_image_tile

    def render(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(preview_service, "render_image_tile", render)
    service = PreviewService()
    source = picture()
    asset = service.upload(source)
    document = DisplayDocument(session_id="editor", image=ImageLayer(image_id=asset["image_id"],
        box=CanvasBox(width=300, height=200), options=RenderOptions(**asset["recommended_options"])))
    service.document(document)
    count = len(calls)
    document.image.box.x = 40
    document.texts = [TextLayer(id="title", text="实时编辑", box=CanvasBox(x=8,y=240,width=200,height=40))]
    result = service.document(document)
    assert len(calls) == count
    assert result["editor_layers"][0]["box"]["x"] == 40
    document.texts[0].text = "修改文字"
    service.document(document)
    assert len(calls) == count
    for update in ("brightness", "background", "rotation"):
        if update == "background":
            document.background = "red"
        elif update == "rotation":
            document.image.options.rotation = 90
        else:
            document.image.options.brightness = 0.8
        result = service.document(document)
        count += 1
        assert len(calls) == count
        assert service.preview(result["preview_id"]).frame == render_document(document, decode_cached_image(source)).image.frame


def test_cached_source_still_checks_expiration(monkeypatch):
    service = PreviewService()
    asset = service.upload(picture())
    document = DisplayDocument(session_id="editor", image=ImageLayer(image_id=asset["image_id"]))
    monkeypatch.setattr(preview_service, "decode_cached_image", lambda data: (_ for _ in ()).throw(AssertionError("redecoded cached source")))
    service.document(document)
    created, source = service._images[asset["image_id"]]
    service._images[asset["image_id"]] = (created - 1801, source)
    import pytest
    with pytest.raises(LookupError, match="原图缓存已过期"):
        service.document(document)
