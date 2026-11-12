"""验证多图独立参数、文字上层、资源上限和最终位面一致性。"""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server import preview_service
from server.app import create_app
from server.models import DisplayDocument, FRAME_BYTES, PLANE_BYTES, RenderOptions
from server.preview_service import PreviewService
from server.rendering import BLACK, RED, WHITE, unpack_frame


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(preview_service, "recommend_options", lambda *args: RenderOptions(resample="pixel"))
    return PreviewService()


def upload(service, color):
    data = io.BytesIO()
    Image.new("RGB", (80, 60), color).save(data, "PNG")
    return service.upload(data.getvalue())


def layer(asset, identifier, box=None):
    return {"id": identifier, "image_id": asset["image_id"], "box": box or {"x": 0, "y": 0, "width": 400, "height": 300},
            "options": asset["recommended_options"]}


def test_images_render_in_order_with_text_always_above_them(service):
    black, red = upload(service, BLACK), upload(service, RED)
    document = DisplayDocument.model_validate({"session_id": "multilayer", "images": [layer(black, "base"),
        layer(red, "patch", {"x": 40, "y": 60, "width": 160, "height": 120})],
        "texts": [{"id": "title", "text": "Hello 示例", "color": "white", "auto_size": True,
                   "box": {"x": 50, "y": 65, "width": 120, "height": 40}}]})
    originals = [image.model_dump() for image in document.images]
    result = service.document(document)
    assert [item["id"] for item in result["editor_layers"]] == ["base", "patch", "title"]
    frame = service.preview(result["preview_id"]).frame
    picture = unpack_frame(frame)
    assert picture.getpixel((5, 5)) == BLACK
    assert picture.getpixel((100, 150)) == RED
    assert WHITE in picture.crop((50, 65, 190, 105)).get_flattened_data()
    assert len(frame) == FRAME_BYTES
    assert not any(a & b for a, b in zip(frame[:PLANE_BYTES], frame[PLANE_BYTES:]))
    png = Image.open(io.BytesIO(base64.b64decode(result["png"].split(",", 1)[1])))
    assert png.tobytes() == picture.tobytes()
    assert [image.model_dump() for image in document.images] == originals


def test_all_eight_sources_survive_uploads_and_have_independent_options(service):
    assets = [upload(service, RED if index % 2 else BLACK) for index in range(8)]
    layers = [layer(asset, str(index), {"x": index % 4 * 100, "y": index // 4 * 150, "width": 100, "height": 150})
              for index, asset in enumerate(assets)]
    layers[3]["options"] = {**layers[3]["options"], "brightness": 0.8, "rotation": 90}
    document = DisplayDocument.model_validate({"session_id": "eight", "images": layers})
    result = service.document(document)
    assert len(result["editor_layers"]) == 8
    assert result["applied_images"]["3"]["brightness"] == 0.8
    assert result["applied_images"]["2"]["brightness"] == 1
    assert len(service._layers) == 8


def test_edits_recompute_only_the_changed_image(service, monkeypatch):
    left, right = upload(service, RED), upload(service, BLACK)
    document = DisplayDocument.model_validate({"session_id": "cache", "images": [
        layer(left, "left", {"x": 0, "y": 0, "width": 160, "height": 120}),
        layer(right, "right", {"x": 200, "y": 0, "width": 160, "height": 120})]})
    calls = []
    original = preview_service.render_image_tile
    def render(image, target, background, prepared):
        calls.append(target.id)
        return original(image, target, background, prepared)
    monkeypatch.setattr(preview_service, "render_image_tile", render)
    service.document(document)
    assert calls == ["left", "right"]
    document.images[0].options.contrast = 1.2
    service.document(document)
    assert calls == ["left", "right", "left"]
    document.images[1].box.y = 10
    service.document(document)
    assert calls == ["left", "right", "left"]


def test_clear_each_content_type_preserves_the_other(service):
    asset = upload(service, RED)
    document = DisplayDocument.model_validate({"session_id": "clear", "images": [layer(asset, "picture")],
        "texts": [{"id": "caption", "text": "Hello", "auto_size": True}]})
    service.document(document)
    text_only = document.model_copy(update={"images": []})
    result = service.document(text_only)
    assert [item["id"] for item in result["editor_layers"]] == ["caption"]
    assert result["counts"]["red"] == 0 and result["counts"]["black"] > 0
    image_only = document.model_copy(update={"texts": []})
    result = service.document(image_only)
    assert [item["id"] for item in result["editor_layers"]] == ["picture"]


def test_api_rejects_conflicting_ids_and_more_than_eight_images(tmp_path, service):
    asset = upload(service, RED)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        for document in [
            {"images": [layer(asset, "same"), layer(asset, "same")]},
            {"images": [layer(asset, "title")], "texts": [{"id": "title"}]},
            {"images": [layer(asset, str(index)) for index in range(9)]},
            {"image": layer(asset, "legacy"), "images": [layer(asset, "new")]},
        ]:
            assert client.post("/api/documents/render", json={"session_id": "invalid", **document}).status_code == 422
