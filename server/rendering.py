import io
from collections import Counter
from dataclasses import dataclass

import numpy as np

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from .models import HEIGHT, PLANE_BYTES, WIDTH, RenderOptions
from .image_detail import sample_details
from .color_math import analyze, select_hue, accent_levels, gray_threshold, map_colors

MAX_PIXELS = 40_000_000
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (220, 0, 0)
DETAIL_RADIUS = 1.2
DETAIL_GAIN = 3.2
DETAIL_NOISE_FLOOR = 2
WHITE_SPECKLE_AREA = 12
WHITE_SPECKLE_CONTRAST = 20


@dataclass(frozen=True)
class RenderedImage:
    frame: bytes
    png: bytes
    counts: dict[str, int]
    accent_hue: float | None


@dataclass(frozen=True)
class PreparedImage:
    canvas: Image.Image
    bounds: tuple
    rgb: Image.Image | None = None
    original: Image.Image | None = None
    alpha: Image.Image | None = None
    reference: Image.Image | None = None
    coverage: Image.Image | None = None


def render_image(data: bytes, options: RenderOptions) -> RenderedImage:
    """图片边界在解码前限制尺寸；预览始终从最终位面生成。"""
    image = decode_image(data)
    canvas = compose_image(image, options)
    quantized, hue = quantize_image(canvas, options)
    return finish_frame(quantized, hue)


def quantize_image(canvas: Image.Image, options: RenderOptions):
    channels = analyze(canvas)
    reference = canvas.info.get("tone_reference", canvas)
    original = analyze(reference)
    coverage = canvas.info.get("coverage")
    hue = select_hue(original, options, coverage)
    shadow, highlight = accent_levels(original, coverage, hue)
    threshold = gray_threshold(analyze(canvas.info.get("detail_reference", reference)), coverage, hue)
    luminance = canvas.convert("L")
    # 只在实际图片内部计算邻域，留白边缘不应生成原图没有的描边。
    bounds = canvas.info.get("content_bounds", (0, 0, canvas.width, canvas.height))
    local = luminance.copy()
    local.paste(luminance.crop(bounds).filter(ImageFilter.GaussianBlur(DETAIL_RADIUS)), bounds[:2])
    broad = luminance.copy()
    broad.paste(luminance.crop(bounds).filter(ImageFilter.GaussianBlur(3)), bounds[:2])
    details = np.maximum(0, np.asarray(ImageChops.lighter(local, broad), dtype=np.int16).reshape(-1) -
                         np.asarray(luminance, dtype=np.int16).reshape(-1) - DETAIL_NOISE_FLOOR) * DETAIL_GAIN
    mapped = map_colors(channels, hue, options, details, shadow, highlight)
    result = _palette_colors(channels, mapped, details, canvas.size, options, threshold)
    if not options.dither:
        # 白色必须得到未锐化原图的支持，避免把滤波过冲误画成高光、白洞或边缘白线。
        source_mapped = map_colors(original, hue, options, np.zeros(len(original.rgb)), shadow, highlight)
        source_colors = _palette_colors(original, source_mapped, np.zeros(len(original.rgb)), canvas.size, options, threshold)
        white = Image.fromarray((np.all(np.asarray(result) == 255, axis=2) * 255).astype(np.uint8))
        result.paste(source_colors, mask=white)
    if not options.dither:
        result = _clean_artifacts(result, canvas.info.get("detail_reference", reference))
    if coverage:
        result.paste(canvas.info["background"], mask=coverage.point(lambda alpha: 255 if alpha == 0 else 0))
    return result, hue


def _palette_colors(channels, mapped_pixels, details, size, options, threshold):
    mapped = Image.fromarray(mapped_pixels.reshape(size[1], size[0], 3))
    palette = Image.new("P", (1, 1))
    palette.putpalette(list(BLACK + WHITE + RED) + [0, 0, 0] * 253)
    dither = Image.Dither.FLOYDSTEINBERG if options.dither else Image.Dither.NONE
    quantized = np.asarray(mapped.quantize(palette=palette, dither=dither).convert("RGB")).reshape(-1, 3).copy()
    values = np.maximum(0, np.rint(np.rint(channels.luminance) - details)).astype(np.uint8)
    gray_image = Image.fromarray(values.reshape(size[1], size[0]))
    grayscale = (gray_image.convert("1", dither=dither) if options.dither else
                 gray_image.point(lambda value: 255 if value > threshold else 0, mode="1"))
    # 未参与重点色或中间调映射的区域独立使用黑白量化，纯灰度图保持黑白输出。
    use_gray = ((mapped_pixels[:, 0] == mapped_pixels[:, 1]) &
                ~np.all(mapped_pixels == 0, axis=1) & ~np.all(mapped_pixels == 255, axis=1))
    quantized[use_gray] = np.where(np.asarray(grayscale).reshape(-1, 1)[use_gray], 255, 0)
    exact = np.all(channels.rgb == 0, axis=1) | np.all(channels.rgb == 255, axis=1)
    quantized[exact] = channels.rgb[exact]
    return Image.fromarray(quantized.reshape(size[1], size[0], 3))


def _clean_artifacts(image, reference):
    """清理缺少原图支持的孤点、末梢和小白洞，保留真实高反差细线。"""
    width, height = image.size
    colors = list(image.get_flattened_data())
    source = list(reference.convert("RGB").get_flattened_data())
    cleaned = colors.copy()
    offsets = (-width - 1, -width, -width + 1, -1, 1, width - 1, width, width + 1)
    labels = image.convert("L")
    for replacement in (BLACK, WHITE, RED):
        label = Image.new("RGB", (1, 1), replacement).convert("L").getpixel((0, 0))
        mask = labels.point(lambda value: int(value == label))
        neighbors = Image.new("L", image.size)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    neighbors = ImageChops.add(neighbors, ImageChops.offset(mask, dx, dy))
        candidates = ImageChops.multiply(neighbors.point(lambda count: 255 if count >= 7 else 0),
                                         mask.point(lambda value: 0 if value else 255))
        for border in ((0, 0, width, 1), (0, height - 1, width, height),
                       (0, 0, 1, height), (width - 1, 0, width, height)):
            candidates.paste(0, border)
        data = candidates.tobytes()
        index = data.find(b"\xff")
        while index >= 0:
            surrounding = [source[index + offset] for offset in offsets if colors[index + offset] == replacement]
            contrast = max(abs(source[index][channel] - sum(pixel[channel] for pixel in surrounding) / len(surrounding))
                           for channel in range(3))
            if contrast < 32:
                cleaned[index] = replacement
            index = data.find(b"\xff", index + 1)
    result = Image.new("RGB", image.size)
    result.putdata(_fill_white_speckles(cleaned, source, width, height))
    return result


def _fill_white_speckles(colors, source, width, height):
    """填补同色区域里缺少原图色差支持的小白洞，保留眼睛、高光和文字等真实白色。"""
    result = colors.copy()
    for component in _small_white_components(colors, width, height):
        area = len(component)
        border = {ny * width + nx for index in component
                  for ny in range(index // width - 1, index // width + 2)
                  for nx in range(index % width - 1, index % width + 2)
                  if colors[ny * width + nx] != WHITE}
        replacement, count = Counter(colors[index] for index in border).most_common(1)[0]
        contrast = max(abs(sum(source[index][channel] for index in component) / area -
                           sum(source[index][channel] for index in border) / len(border)) for channel in range(3))
        if count / len(border) >= 0.65 and contrast < WHITE_SPECKLE_CONTRAST:
            for index in component:
                result[index] = replacement
    return result


def _small_white_components(colors, width, height):
    """按行查找白色连续段并合并八邻域，避免逐点遍历整片白色背景。"""
    mask = bytes(color == WHITE for color in colors)
    runs, parents, previous = [], [], []

    def root(identifier):
        while parents[identifier] != identifier:
            parents[identifier] = parents[parents[identifier]]
            identifier = parents[identifier]
        return identifier

    for y in range(height):
        row, stop = y * width, (y + 1) * width
        start = mask.find(b"\x01", row, stop)
        current, cursor = [], 0
        while start >= 0:
            end = mask.find(b"\x00", start, stop)
            if end < 0:
                end = stop
            left, right = start - row, end - row
            identifier = len(parents)
            parents.append(identifier)
            runs.append((y, left, right))
            current.append(identifier)
            while cursor < len(previous) and runs[previous[cursor]][2] < left:
                cursor += 1
            for index in range(cursor, len(previous)):
                prior = previous[index]
                if runs[prior][1] > right:
                    break
                parents[root(prior)] = root(identifier)
            start = mask.find(b"\x01", end, stop)
        previous = current

    groups = {}
    for identifier, (y, left, right) in enumerate(runs):
        group = groups.setdefault(root(identifier), [0, False, []])
        group[0] += right - left
        group[1] |= y == 0 or y == height - 1 or left == 0 or right == width
        if group[0] <= WHITE_SPECKLE_AREA:
            group[2].extend(range(y * width + left, y * width + right))
        else:
            group[2].clear()
    return [pixels for area, edge, pixels in groups.values() if area <= WHITE_SPECKLE_AREA and not edge]


def finish_frame(image: Image.Image, hue: float | None = None) -> RenderedImage:
    """封装最终三色画布，文字与图片共享同一份传输位面。"""
    colors = np.asarray(image)
    frame = _pack(colors)
    preview = unpack_frame(frame)
    stream = io.BytesIO()
    preview.save(stream, format="PNG")
    counts = {name: int(np.count_nonzero(np.all(colors == color, axis=2)))
              for name, color in (("black", BLACK), ("white", WHITE), ("red", RED))}
    return RenderedImage(frame, stream.getvalue(),
                         counts, hue)


def decode_image(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("仅支持 JPEG、PNG、WebP 图片。")
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("图片不能超过 4000 万像素。")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("请上传静态图片，不支持动画。")
            return _normalize(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("图片无法解码，请重新导出为 PNG 或 JPEG。") from error


def decode_cached_image(data: bytes) -> Image.Image:
    """缓存仅接收已完整解码验证的不可变字节，此处只执行解码和方向归一。"""
    with Image.open(io.BytesIO(data)) as image:
        return _normalize(image)


def _normalize(image: Image.Image) -> Image.Image:
    source_format = image.format
    result = ImageOps.exif_transpose(image).convert("RGBA")
    result.info["source_format"] = source_format
    return result


def compose_image(image: Image.Image, options: RenderOptions, size=(WIDTH, HEIGHT),
                  background=WHITE, zoom=1, offset=(0, 0)) -> Image.Image:
    """直接采样可见源区域，倍率不会扩大输出缓冲；透明与留白使用画布墨色。"""
    return compose_prepared(prepare_image(image, options, size, background, zoom, offset), options)


def prepare_image(image: Image.Image, options: RenderOptions, size=(WIDTH, HEIGHT),
                  background=WHITE, zoom=1, offset=(0, 0)) -> PreparedImage:
    """几何采样与调色分离，连续调整亮度等参数时复用原尺寸细节与透明通道。"""
    image = image.rotate(-options.rotation, expand=True)
    method = Image.Resampling.NEAREST if options.resample == "pixel" else Image.Resampling.LANCZOS
    ratio = (min if options.fit == "contain" else max)(size[0] / image.width, size[1] / image.height) * zoom
    left = (size[0] - image.width * ratio) / 2 + offset[0] * size[0]
    top = (size[1] - image.height * ratio) / 2 + offset[1] * size[1]
    bounds = (max(0, round(left)), max(0, round(top)),
              min(size[0], round(left + image.width * ratio)), min(size[1], round(top + image.height * ratio)))
    canvas = Image.new("RGB", size, background)
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return PreparedImage(canvas, bounds)
    source = (max(0, (bounds[0] - left) / ratio), max(0, (bounds[1] - top) / ratio),
              min(image.width, (bounds[2] - left) / ratio), min(image.height, (bounds[3] - top) / ratio))
    tile = image.resize((bounds[2] - bounds[0], bounds[3] - bounds[1]), method, box=source).convert("RGBA")
    alpha = tile.getchannel("A")
    rgb = tile.convert("RGB")
    reference = canvas.copy()
    original = image.resize(tile.size, Image.Resampling.NEAREST if options.resample == "pixel" else Image.Resampling.BOX,
                            box=source).convert("RGBA")
    reference.paste(original.convert("RGB"), bounds[:2], original.getchannel("A"))
    if options.resample == "smooth" and ratio < 1 and alpha.getextrema() == (255, 255):
        rgb = sample_details(image, tile.size, source)
    coverage = Image.new("L", size)
    coverage.paste(alpha, bounds[:2])
    return PreparedImage(canvas, bounds, rgb, original, alpha, reference, coverage)


def compose_prepared(prepared: PreparedImage, options: RenderOptions) -> Image.Image:
    canvas = prepared.canvas.copy()
    if prepared.rgb is None:
        return canvas
    tone_reference = canvas.copy()
    toned = ImageEnhance.Contrast(ImageEnhance.Brightness(prepared.original.convert("RGB")).enhance(options.brightness)).enhance(options.contrast)
    tone_reference.paste(toned, prepared.bounds[:2], prepared.original.getchannel("A"))
    rgb = ImageEnhance.Contrast(ImageEnhance.Brightness(prepared.rgb).enhance(options.brightness)).enhance(options.contrast)
    canvas.paste(rgb, prepared.bounds[:2], prepared.alpha)
    canvas.info.update(content_bounds=prepared.bounds, detail_reference=prepared.reference,
                       tone_reference=tone_reference, coverage=prepared.coverage,
                       background=prepared.canvas.getpixel((0, 0)))
    return canvas


def _pack(pixels: np.ndarray) -> bytes:
    colors = np.asarray(pixels, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
    return b"".join(np.packbits(np.all(colors == color, axis=2), axis=1, bitorder="big").tobytes()
                    for color in (BLACK, RED))


def unpack_frame(frame: bytes) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    image.paste(BLACK, (0, 0), Image.frombytes("1", image.size, frame[:PLANE_BYTES]))
    image.paste(RED, (0, 0), Image.frombytes("1", image.size, frame[PLANE_BYTES:]))
    return image
