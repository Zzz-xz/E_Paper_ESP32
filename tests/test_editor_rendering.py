"""覆盖公开画布接口和有意义的小面积细节，不依赖用户提供的图片。"""
import io
import math

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from server.app import create_app
from server.composition import INKS, render_document
from server.models import DisplayDocument, RenderOptions
from server.optimization import recommend_options
from server.image_detail import sample_details
from server.rendering import BLACK, RED, WHITE, _clean_artifacts, compose_image, quantize_image, unpack_frame


@pytest.mark.parametrize("foreground,background", [(a, b) for a in INKS for b in INKS if a != b])
def test_palette_controls_blank_and_default_text_without_inverting_photo(foreground, background):
    document = DisplayDocument.model_validate({"session_id": "palette", "foreground": foreground, "background": background,
        "image": {"image_id": "source", "box": {"x": 0, "y": 0, "width": 100, "height": 100}},
        "texts": [{"id": "text", "text": "Hello", "box": {"x": 150, "y": 150, "width": 150, "height": 50}}]})
    source = Image.new("RGB", (100, 100), WHITE)
    ImageDraw.Draw(source).rectangle((0, 0, 49, 99), fill=BLACK)
    image = unpack_frame(render_document(document, source).image.frame)
    assert image.getpixel((20, 50)) == BLACK
    assert image.getpixel((80, 50)) == WHITE
    assert image.getpixel((399, 299)) == INKS[background]
    assert INKS[foreground] in image.crop((150, 150, 300, 200)).get_flattened_data()


def test_transparency_and_contain_padding_use_selected_background():
    source = Image.new("RGBA", (20, 40), (0, 0, 255, 0))
    ImageDraw.Draw(source).rectangle((5, 5, 14, 34), fill=(255, 255, 255, 255))
    tile = compose_image(source, RenderOptions(), (100, 100), RED)
    rendered, _ = quantize_image(tile, RenderOptions())
    assert rendered.getpixel((0, 0)) == RED
    assert rendered.getpixel((26, 0)) == RED
    assert rendered.getpixel((50, 50)) == WHITE


def test_red_padding_does_not_override_photo_accent_or_manual_strength():
    source = Image.new("RGB", (20, 40), (30, 100, 220))
    tile = compose_image(source, RenderOptions(), (100, 100), RED)
    image, hue = quantize_image(tile, RenderOptions())
    assert 190 < hue < 250
    assert image.getpixel((0, 0)) == RED
    source = Image.new("RGB", (20, 40), RED)
    options = RenderOptions(accent_strength=0)
    image, _ = quantize_image(compose_image(source, options, (100, 100), RED), options)
    assert image.getpixel((50, 50)) == BLACK
    assert image.getpixel((0, 0)) == RED


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("zoom", [0.25, 1, 4])
def test_zoom_is_bounded_to_output_frame_and_preserves_padding(rotation, zoom):
    tile = compose_image(Image.new("RGB", (600, 300), "red"), RenderOptions(rotation=rotation),
                         (120, 80), BLACK, zoom, (0.1, -0.1))
    assert tile.size == (120, 80)
    assert set(tile.get_flattened_data()) <= {BLACK, (255, 0, 0)}


def test_small_warm_shapes_and_tooth_separators_survive_without_dither():
    source = Image.new("RGB", (1200, 900), (242, 153, 33))
    draw = ImageDraw.Draw(source)
    draw.rectangle((90, 90, 350, 780), fill=(158, 105, 26))
    draw.ellipse((450, 400, 1050, 880), fill=(250, 100, 20))
    centers = [(660, 560), (840, 560), (660, 730), (840, 730)]
    for x, y in centers:
        vertices = [(x + math.cos(-math.pi / 2 + i * math.pi / 5) * (42 if i % 2 == 0 else 18),
                     y + math.sin(-math.pi / 2 + i * math.pi / 5) * (42 if i % 2 == 0 else 18)) for i in range(10)]
        draw.polygon(vertices, fill=(190, 0, 0))
    draw.rectangle((480, 150, 1020, 300), fill=WHITE)
    draw.line((490, 225, 1010, 225), fill=(180, 180, 180), width=6)
    options = recommend_options(source)
    result, _ = quantize_image(compose_image(source, options), options)
    assert not options.dither
    assert result.getpixel((5, 5)) == WHITE
    assert result.getpixel((70, 100)) == RED
    for x, y in centers:
        assert result.getpixel((round(x / 3), round(y / 3))) == BLACK
    assert sum(result.getpixel((x, 75)) == BLACK for x in range(170, 330)) > 100


def test_no_false_edge_along_contain_padding():
    source = Image.new("RGB", (160, 90), (242, 153, 33))
    draw = ImageDraw.Draw(source)
    draw.rectangle((50, 10, 100, 80), fill=(150, 95, 24))
    image, _ = quantize_image(compose_image(source, RenderOptions()), RenderOptions())
    assert len(set(image.getpixel((5, y)) for y in range(300))) == 1


def test_new_upload_preserves_complete_image_and_padding_color():
    source = Image.new("RGB", (160, 90), (240, 150, 60))
    options = recommend_options(source)
    assert options.fit == "contain"
    output, _ = quantize_image(compose_image(source, options), options)
    assert output.getpixel((0, 0)) == WHITE
    assert output.getpixel((200, 150)) == RED


@pytest.mark.parametrize("background,body,stroke", [
    ((242, 153, 33), (158, 105, 26), (147, 97, 24)),
    ((110, 195, 250), (45, 95, 155), (35, 80, 140)),
    ((110, 220, 110), (40, 125, 40), (28, 108, 28)),
])
def test_low_contrast_texture_inside_same_color_object_is_not_flat_red(background, body, stroke):
    source = Image.new("RGB", (1200, 900), background)
    draw = ImageDraw.Draw(source)
    draw.rectangle((150, 180, 1050, 720), fill=body)
    for y in range(230, 690, 42):
        draw.line((210, y, 990, y + 15), fill=stroke, width=6)
    options = recommend_options(source)
    output, _ = quantize_image(compose_image(source, options), options)
    interior = list(output.crop((80, 85, 320, 225)).get_flattened_data())
    assert interior.count(BLACK) > 250
    assert interior.count(RED) > 5000


def test_noise_cleanup_removes_unsupported_dot_but_keeps_real_black_detail():
    source = Image.new("RGB", (20, 20), (132, 132, 132))
    source.putpixel((6, 6), (125, 125, 125))
    source.putpixel((14, 14), BLACK)
    output, _ = quantize_image(source, RenderOptions())
    assert output.getpixel((6, 6)) == WHITE
    assert output.getpixel((14, 14)) == BLACK


def test_small_false_white_holes_are_removed_but_real_highlights_survive():
    source = Image.new("RGB", (32, 24), (180, 90, 30))
    output = Image.new("RGB", source.size, RED)
    draw = ImageDraw.Draw(output)
    draw.rectangle((5, 5, 6, 7), fill=WHITE)
    draw.rectangle((20, 5, 21, 7), fill=WHITE)
    ImageDraw.Draw(source).rectangle((20, 5, 21, 7), fill=(250, 250, 250))
    cleaned = _clean_artifacts(output, source)
    assert cleaned.getpixel((5, 6)) == RED
    assert cleaned.getpixel((20, 6)) == WHITE


def test_source_edge_does_not_gain_white_outline_after_tiled_enhancement():
    source = Image.new("RGB", (1200, 900), (165, 95, 25))
    ImageDraw.Draw(source).rectangle((0, 0, 600, 899), fill=(35, 35, 35))
    options = RenderOptions(fit="cover")
    output, _ = quantize_image(compose_image(source, options), options)
    assert WHITE not in output.get_flattened_data()
    assert BLACK in output.get_flattened_data()
    assert RED in output.get_flattened_data()


def test_colored_photo_keeps_neutral_midtones_between_black_and_white():
    source = Image.new("RGB", (400, 300), (30, 150, 210))
    draw = ImageDraw.Draw(source)
    draw.rectangle((50, 50, 350, 250), fill=(225, 225, 225))
    draw.rectangle((100, 100, 300, 200), fill=(145, 145, 145))
    draw.rectangle((150, 125, 250, 175), fill=(25, 25, 25))
    output, _ = quantize_image(source, RenderOptions())
    assert output.getpixel((60, 60)) == WHITE
    assert output.getpixel((110, 110)) == RED
    assert output.getpixel((200, 150)) == BLACK


def test_smooth_blue_background_does_not_turn_into_black_white_patches():
    source = Image.new("RGB", (400, 300))
    source.putdata([(35 + y // 12, 115 + y // 10, 200 + x // 10) for y in range(300) for x in range(400)])
    output, _ = quantize_image(source, RenderOptions())
    assert set(output.get_flattened_data()) == {RED}


def test_bright_cyan_highlights_remain_distinct_from_blue_midtone():
    source = Image.new("RGB", (400, 300), (0, 18, 45))
    draw = ImageDraw.Draw(source)
    draw.rectangle((70, 70, 330, 230), fill=(20, 110, 200))
    draw.rectangle((200, 100, 240, 140), fill=(160, 225, 255))
    output, _ = quantize_image(source, RenderOptions())
    assert output.getpixel((10, 10)) == BLACK
    assert output.getpixel((100, 100)) == RED
    assert output.getpixel((220, 120)) == WHITE


def test_deep_and_light_red_regions_are_not_split_into_red_and_white():
    source = Image.new("RGB", (400, 300), (20, 150, 210))
    draw = ImageDraw.Draw(source)
    draw.rectangle((80, 60, 320, 170), fill=(255, 225, 60))
    draw.rectangle((80, 170, 200, 210), fill=(220, 15, 15))
    draw.rectangle((201, 170, 320, 210), fill=(230, 100, 100))
    options = recommend_options(source)
    output, _ = quantize_image(compose_image(source, options), options)
    assert output.getpixel((120, 190)) == RED
    assert output.getpixel((280, 190)) == RED
    assert output.getpixel((200, 100)) == WHITE
    assert output.getpixel((20, 20)) == BLACK


def test_original_source_tiles_merge_in_their_original_positions():
    source = Image.new("RGB", (2400, 1800))
    draw = ImageDraw.Draw(source)
    colors = [(30 + column * 60, 40 + row * 70, 50 + (row + column) * 30)
              for row in range(3) for column in range(3)]
    for index, color in enumerate(colors):
        x, y = index % 3 * 800, index // 3 * 600
        draw.rectangle((x, y, x + 799, y + 599), fill=color)
    output = sample_details(source, (400, 300), (0, 0, 2400, 1800))
    for index, color in enumerate(colors):
        assert output.getpixel((round((index % 3 + 0.5) * 400 / 3), index // 3 * 100 + 50)) == color


def test_overlapping_tiles_match_whole_image_filter_without_seams():
    source = Image.new("RGB", (613, 471))
    source.putdata([((x * 3 + y) % 256, (x + y * 2) % 256, (x * 2 + y * 3) % 256)
                    for y in range(source.height) for x in range(source.width)])
    source = source.convert("RGBA")
    tiled = sample_details(source, (320, 240), (0, 0, 613, 471))
    working = source.resize((640, 480), Image.Resampling.LANCZOS).convert("RGB")
    sharpened = working.filter(ImageFilter.UnsharpMask(radius=1.1, percent=80, threshold=3))
    whole = ImageChops.lighter(working.filter(ImageFilter.MinFilter(3)),
                               ImageChops.darker(working.filter(ImageFilter.MaxFilter(3)), sharpened)).resize((320, 240), Image.Resampling.BOX)
    difference = ImageChops.difference(tiled, whole)
    statistics = ImageStat.Stat(difference)
    # 独立浮点重采样会在高频边缘产生局部舍入差，但拼接线不能出现整体亮暗跳变。
    assert max(statistics.mean) < 0.25
    assert max(statistics.rms) < 1
    for x in range(64, 320, 64):
        assert max(ImageStat.Stat(difference.crop((x - 1, 0, x + 1, 240))).mean) < 0.5
    for y in range(64, 240, 64):
        assert max(ImageStat.Stat(difference.crop((0, y - 1, 320, y + 1))).mean) < 0.5


def test_api_validates_new_fields_and_returns_applied_manual_options(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        data = io.BytesIO()
        Image.new("RGB", (30, 20), (30, 100, 220)).save(data, "PNG")
        asset = client.post("/api/images", files={"file": ("test.png", data.getvalue(), "image/png")}).json()
        assert not asset["recommended_options"]["dither"]
        document = {"session_id": "controls", "image": {"image_id": asset["image_id"], "options": {"brightness": 0.8, "dither": True}}}
        result = client.post("/api/documents/render", json=document).json()
        assert result["applied_options"]["brightness"] == 0.8
        assert result["applied_options"]["dither"]
        document["image"]["recommendation"] = "auto"
        assert client.post("/api/documents/render", json=document).json()["applied_options"]["dither"]
        for invalid in ({"zoom": 4.1}, {"zoom": 0.24}, {"offset_x": 4}, {"recommendation": "unknown"}):
            changed = {**document, "image": {**document["image"], **invalid}}
            assert client.post("/api/documents/render", json=changed).status_code == 422
        assert client.post("/api/documents/render", json={"session_id": "bad", "foreground": "red", "background": "red"}).status_code == 422
