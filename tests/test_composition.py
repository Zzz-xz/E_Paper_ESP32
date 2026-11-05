import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from server.app import create_app
from server.composition import render_document
from server.models import DisplayDocument, FRAME_BYTES, PLANE_BYTES
from server.rendering import RED, WHITE, unpack_frame


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def text(identifier="title", **updates):
    return {"id": identifier, "text": "Hello 墨水屏幕", "box": {"x": 8, "y": 212, "width": 384, "height": 64},
            "font_size": 24, "color": "red", **updates}


def upload(client):
    stream = io.BytesIO()
    Image.new("RGB", (120, 80), (250, 140, 30)).save(stream, "PNG")
    response = client.post("/api/images", files={"file": ("photo.png", stream.getvalue(), "image/png")})
    assert response.status_code == 200
    return response.json()


def test_text_only_chinese_and_exact_ink():
    document = DisplayDocument.model_validate({"session_id": "text-only", "texts": [text()]})
    result = render_document(document, None)
    assert len(result.image.frame) == FRAME_BYTES
    assert result.image.counts["red"] > 100
    assert result.image.counts["black"] == 0
    assert not any(a & b for a, b in zip(result.image.frame[:PLANE_BYTES], result.image.frame[PLANE_BYTES:]))
    image = unpack_frame(result.image.frame)
    assert image.getpixel((0, 0)) == WHITE
    assert set(image.get_flattened_data()) == {WHITE, RED}
    with Image.open(io.BytesIO(result.image.png)) as preview:
        assert preview.tobytes() == image.tobytes()


def test_upload_recommendation_and_mixed_document(client):
    asset = upload(client)
    assert client.get(f"/api/images/{asset['image_id']}/source").status_code == 200
    document = {"session_id": "mixed", "image": {"image_id": asset["image_id"],
        "box": {"x": 0, "y": 0, "width": 400, "height": 180}, "options": asset["recommended_options"]}, "texts": [text()]}
    response = client.post("/api/documents/render", json=document)
    assert response.status_code == 200
    result = response.json()
    assert [layer["id"] for layer in result["editor_layers"]] == ["image", "title"]
    assert result["warnings"] == []
    image = Image.open(io.BytesIO(base64.b64decode(result["png"].split(",")[1])))
    assert image.getpixel((0, 200)) == WHITE
    assert RED in image.crop((8, 212, 392, 276)).get_flattened_data()
    assert client.post(f"/api/images/{asset['image_id']}/render", json=asset["recommended_options"]).status_code == 200


def test_latest_preview_is_per_document_not_per_slider_request(client):
    first = client.post("/api/documents/render", json={"session_id": "a", "texts": [text()]}).json()
    other = client.post("/api/documents/render", json={"session_id": "b", "texts": [text()]}).json()
    for size in range(12, 22):
        latest = client.post("/api/documents/render", json={"session_id": "a", "texts": [text(font_size=size)]}).json()
    service = client.app.state.previews
    with pytest.raises(LookupError):
        service.preview(first["preview_id"])
    assert service.preview(other["preview_id"])
    assert service.preview(latest["preview_id"])


def test_document_boundary_rejects_invalid_geometry_and_colors(client):
    for layer in (text(color="blue"), text(font_size=100), text(box={"x": 390, "y": 0, "width": 40, "height": 30})):
        assert client.post("/api/documents/render", json={"session_id": "bad", "texts": [layer]}).status_code == 422
    assert client.post("/api/documents/render", json={"session_id": "bad", "texts": [text(), text()]}).status_code == 422
    assert client.post("/api/documents/render", json={"session_id": "missing", "image": {"image_id": "missing"}}).status_code == 410


def test_text_wrap_clipping_warning_and_black_text_stays_black(client):
    response = client.post("/api/documents/render", json={"session_id": "clipped", "texts": [text(
        text="很多中文需要自动换行" * 10, color="black", box={"x": 0, "y": 0, "width": 80, "height": 30})]})
    assert response.status_code == 200
    assert response.json()["warnings"]
    assert response.json()["counts"]["red"] == 0


def test_render_busy_is_visible(client):
    with client.app.state.previews.processing():
        response = client.post("/api/documents/render", json={"session_id": "busy", "texts": [text()]})
    assert response.status_code == 429


def test_source_cache_expires_and_current_preview_can_be_sent(client):
    asset = upload(client)
    service = client.app.state.previews
    with service._cache_lock:
        created, source = service._images[asset["image_id"]]
        service._images[asset["image_id"]] = (created - 1801, source)
    assert client.get(f"/api/images/{asset['image_id']}/source").status_code == 410
    client.post("/api/device/poll")
    response = client.post("/api/display-jobs", json={"preview_id": asset["preview"]["preview_id"]})
    assert response.status_code == 201


@pytest.mark.parametrize("align", ["left", "center", "right"])
@pytest.mark.parametrize("vertical", ["top", "middle", "bottom"])
def test_text_has_independent_horizontal_and_vertical_alignment(align, vertical):
    box = {"x": 50, "y": 50, "width": 200, "height": 120}
    document = DisplayDocument.model_validate({"session_id": "alignment", "texts": [text(
        text="Hello 示例\n第二行", box=box, align=align, vertical_align=vertical, color="black")]})
    result = render_document(document, None)
    region = unpack_frame(result.image.frame).crop((50, 50, 250, 170))
    bounds = ImageChops.difference(region, Image.new("RGB", region.size, WHITE)).getbbox()
    assert bounds
    if align == "left":
        assert bounds[0] <= 2
    elif align == "center":
        assert abs((bounds[0] + bounds[2]) / 2 - 100) <= 2
    else:
        assert abs(bounds[2] - 200) <= 2
    if vertical == "top":
        assert bounds[1] <= 1
    elif vertical == "middle":
        assert abs((bounds[1] + bounds[3]) / 2 - 60) <= 1
    else:
        assert abs(bounds[3] - 120) <= 1


def test_legacy_text_defaults_to_top_and_rejects_invalid_vertical_alignment(client):
    default = {"session_id": "legacy", "texts": [text()]}
    original = client.post('/api/documents/render', json=default).json()['png']
    default['texts'][0]['vertical_align'] = 'top'
    assert client.post('/api/documents/render', json=default).json()['png'] == original
    default['texts'][0]['vertical_align'] = 'center'
    assert client.post('/api/documents/render', json=default).status_code == 422
