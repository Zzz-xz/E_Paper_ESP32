import io
import binascii
import struct

import pytest
from PIL import Image

from server.models import FRAME_BYTES, PLANE_BYTES, RenderOptions
from server.rendering import render_image, unpack_frame


def image_bytes(color, size=(80, 60), mode="RGB", format="PNG"):
    image = Image.new(mode, size, color)
    data = io.BytesIO()
    image.save(data, format=format)
    return data.getvalue()


@pytest.mark.parametrize("color", [(240, 150, 60), (50, 160, 50), (30, 100, 220)])
def test_colored_images_use_red_and_preview_matches_wire(color):
    rendered = render_image(image_bytes(color), RenderOptions(dither=False))
    assert rendered.counts["red"] > 0
    assert len(rendered.frame) == FRAME_BYTES
    assert not any(b & r for b, r in zip(rendered.frame[:PLANE_BYTES], rendered.frame[PLANE_BYTES:]))
    with Image.open(io.BytesIO(rendered.png)) as preview:
        assert preview.tobytes() == unpack_frame(rendered.frame).tobytes()


def test_grayscale_and_explicit_red_style():
    data = image_bytes((120, 120, 120))
    assert render_image(data, RenderOptions()).counts["red"] == 0
    assert render_image(data, RenderOptions(accent_mode="grayscale_red")).counts["red"] > 0


def test_transparent_background_stays_white():
    rendered = render_image(image_bytes((255, 0, 0, 0), mode="RGBA"), RenderOptions())
    assert rendered.counts == {"black": 0, "white": 120000, "red": 0}


def test_contain_and_rotation_preserve_portrait_geometry():
    data = image_bytes((255, 0, 0), size=(40, 80))
    portrait = unpack_frame(render_image(data, RenderOptions(dither=False)).frame)
    assert portrait.getpixel((0, 150)) == (255, 255, 255)
    assert portrait.getpixel((200, 0)) == (220, 0, 0)
    rotated = unpack_frame(render_image(data, RenderOptions(rotation=90, dither=False)).frame)
    assert rotated.getpixel((200, 0)) == (255, 255, 255)
    assert rotated.getpixel((0, 150)) == (220, 0, 0)


def test_invalid_and_animated_images_are_rejected():
    with pytest.raises(ValueError):
        render_image(b"not an image", RenderOptions())
    data = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(data, format="PNG", save_all=True,
                                      append_images=[Image.new("RGB", (2, 2), "blue")])
    with pytest.raises(ValueError, match="静态"):
        render_image(data.getvalue(), RenderOptions())


def test_pixel_mode_does_not_blur_edges():
    rendered = render_image(image_bytes((255, 0, 0), (3, 5)), RenderOptions(resample="pixel", dither=False))
    assert set(unpack_frame(rendered.frame).get_flattened_data()) <= {(255, 255, 255), (220, 0, 0)}


def test_saturated_flat_illustration_keeps_filled_accent_regions():
    rendered = render_image(image_bytes((240, 150, 60)), RenderOptions(accent_strength=0.7, dither=False))
    assert rendered.counts["red"] > 60000


@pytest.mark.parametrize("format", ["JPEG", "WEBP"])
def test_other_supported_formats(format):
    assert render_image(image_bytes((240, 80, 30), format=format), RenderOptions()).counts["red"] > 0


def test_pixel_limit_is_checked_before_loading_image_data():
    data = bytearray(image_bytes((255, 0, 0), size=(1, 1)))
    data[16:24] = struct.pack(">II", 8001, 5000)
    data[29:33] = struct.pack(">I", binascii.crc32(data[12:29]))
    with pytest.raises(ValueError, match="4000 万"):
        render_image(bytes(data), RenderOptions())


def test_phone_exif_orientation_is_applied():
    image = Image.new("RGB", (20, 40), (255, 0, 0))
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, format="JPEG", exif=exif)
    result = unpack_frame(render_image(data.getvalue(), RenderOptions(dither=False)).frame)
    assert result.getpixel((200, 0)) == (255, 255, 255)
    assert result.getpixel((0, 150)) == (220, 0, 0)
