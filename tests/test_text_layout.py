import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.app import create_app
from server.composition import render_document
from server.models import DisplayDocument, FRAME_BYTES
from server.rendering import BLACK, RED, unpack_frame
from server.text_layout import fit_text_boxes, text_tile


def document(text="Hello 墨水屏幕", size=36, box=None, image=False):
    return DisplayDocument.model_validate({"session_id": "auto-text", "image": {
        "image_id": "fixture", "box": {"x": 0, "y": 0, "width": 400, "height": 180},
        "zoom": 1.8, "offset_x": 0.1, "offset_y": -0.1,
        "options": {"rotation": 90, "brightness": 0.8, "contrast": 1.1},
    } if image else None, "texts": [{"id": "title", "text": text, "font_size": size,
        "auto_size": True, "box": box or {"x": 8, "y": 200, "width": 120, "height": 32}}]})


def overlaps(a, b):
    return a.x < b.x + b.width and a.x + a.width > b.x and a.y < b.y + b.height and a.y + a.height > b.y


@pytest.mark.parametrize("size", [8, 24, 36, 72])
def test_auto_text_grows_without_changing_image_and_keeps_all_ink(size):
    original = document(text="示例" if size == 72 else "Hello 墨水屏幕", size=size, image=True)
    fitted = fit_text_boxes(original)
    layer = fitted.texts[0]
    assert fitted.image == original.image
    assert not overlaps(layer.box, fitted.image.box)
    assert layer.box.width >= original.texts[0].box.width
    assert layer.box.height >= original.texts[0].box.height
    assert layer.box.x + layer.box.width <= 400
    assert layer.box.y + layer.box.height <= 300
    tile, clipped = text_tile(layer)
    assert not clipped
    enlarged = layer.model_copy(update={"box": layer.box.model_copy(update={"height": 300})})
    reference, _ = text_tile(enlarged)
    assert sum(tile.getchannel("A").get_flattened_data()) == sum(reference.getchannel("A").get_flattened_data())
    assert fit_text_boxes(fitted) == fitted


def test_multiline_growth_moves_inward_at_bottom_edge():
    original = document("中文第一行\n第二行文字\n+ − 123", 28,
                        {"x": 350, "y": 280, "width": 50, "height": 20})
    fitted = fit_text_boxes(original)
    layer = fitted.texts[0]
    assert layer.box.width > 50 and layer.box.height > 20
    assert layer.box.x < 350 and layer.box.y < 280
    result = render_document(fitted, None)
    assert not result.warnings
    assert result.text_boxes["title"] == layer.box.model_dump()
    assert result.image.counts["black"] > 0


def test_multiple_texts_stay_out_of_image_and_each_other():
    original = document("第一段", 24, image=True)
    second = original.texts[0].model_copy(update={"id": "second", "text": "第二段",
        "box": original.texts[0].box.model_copy(update={"x": 220})})
    original = original.model_copy(update={"texts": [original.texts[0], second]})
    fitted = fit_text_boxes(original)
    assert not overlaps(*[layer.box for layer in fitted.texts])
    assert all(not overlaps(layer.box, fitted.image.box) for layer in fitted.texts)
    assert fitted.image == original.image


def test_api_returns_fitted_boxes_and_exact_preview_frame(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/documents/render", json=document().model_dump())
        assert response.status_code == 200
        result = response.json()
        assert result["text_boxes"]["title"]["width"] > 120
        assert result["editor_layers"][0]["box"] == result["text_boxes"]["title"]
        frame = client.app.state.previews.preview(result["preview_id"]).frame
        preview = Image.open(io.BytesIO(base64.b64decode(result["png"].split(",", 1)[1])))
        assert len(frame) == FRAME_BYTES
        assert unpack_frame(frame).tobytes() == preview.tobytes()


def test_impossible_text_rejects_preview_instead_of_clipping(tmp_path):
    original = document("字" * 500, 72)
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/documents/render", json=original.model_dump())
        assert response.status_code == 422
        assert "无法完整放入空白区域" in response.json()["detail"]
        assert not client.app.state.previews._previews


def test_no_blank_area_never_shrinks_image():
    original = document(image=True)
    original = original.model_copy(update={"image": original.image.model_copy(update={
        "box": original.image.box.model_copy(update={"height": 300})})})
    before = original.model_dump()
    with pytest.raises(ValueError, match="无法完整放入空白区域"):
        fit_text_boxes(original)
    assert original.model_dump() == before


def test_text_layers_render_above_image_for_explicit_legacy_layout():
    original = document("Hello", 24, {"x": 0, "y": 0, "width": 140, "height": 40}, True)
    original = original.model_copy(update={"texts": [original.texts[0].model_copy(update={"auto_size": False})]})
    result = render_document(original, Image.new("RGB", (100, 100), RED))
    assert [layer["id"] for layer in result.editor_layers] == ["image", "title"]
    assert BLACK in unpack_frame(result.image.frame).crop((0, 0, 140, 40)).get_flattened_data()
