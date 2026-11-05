"""有限候选先粗筛、再在实际输出尺寸评估局部细节，避免大色块掩盖细线。"""
from itertools import product

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat

from .models import RenderOptions
from .rendering import WHITE, compose_image, quantize_image

ANALYSIS_SIZE = (128, 96)


def recommend_options(image: Image.Image, base: RenderOptions | None = None,
                      size=(400, 300), background=WHITE, zoom=1, offset=(0, 0)) -> RenderOptions:
    sample = image.convert("RGB").resize(ANALYSIS_SIZE, Image.Resampling.NEAREST)
    options = base or RenderOptions(fit="contain", resample="pixel" if _is_pixel_art(sample) else "smooth")
    neutral = options.model_copy(update={"brightness": 1, "contrast": 1, "accent_strength": 0.85})
    reference = compose_image(image, neutral, size, background, zoom, offset)
    coarse_size = (min(128, size[0]), min(96, size[1]))
    coarse = reference.resize(coarse_size, Image.Resampling.BOX)
    coarse.info["detail_reference"] = reference.info.get("detail_reference", reference).resize(coarse_size, Image.Resampling.BOX)
    coarse.info["tone_reference"] = reference.info.get("tone_reference", reference).resize(coarse_size, Image.Resampling.BOX)
    if "coverage" in reference.info:
        coarse.info["coverage"] = reference.info["coverage"].resize(coarse_size, Image.Resampling.NEAREST)
    if "content_bounds" in reference.info:
        coarse.info["content_bounds"] = tuple(round(value * coarse_size[index % 2] / size[index % 2])
                                               for index, value in enumerate(reference.info["content_bounds"]))
    candidates = [neutral.model_copy(update={"brightness": brightness, "contrast": contrast,
                                            "accent_strength": strength})
                  for brightness, contrast, strength in product((0.9, 1.0, 1.1), (1.0, 1.2), (0.7, 0.9))]
    def score(candidate, target):
        adjusted = ImageEnhance.Contrast(ImageEnhance.Brightness(target).enhance(candidate.brightness)).enhance(candidate.contrast)
        adjusted.info = target.info.copy()
        raw = target.info.get("detail_reference", target)
        adjusted.info["tone_reference"] = ImageEnhance.Contrast(ImageEnhance.Brightness(raw).enhance(candidate.brightness)).enhance(candidate.contrast)
        result, _ = quantize_image(adjusted, candidate)
        return _error(target.info.get("detail_reference", target), result)

    finalists = sorted(candidates, key=lambda candidate: score(candidate, coarse))[:3]
    return min([neutral, *finalists], key=lambda candidate: score(candidate, reference))


def _error(reference, candidate):
    original = reference.convert("L")
    rendered = candidate.convert("L")
    tone = _mean_square(ImageChops.difference(original, rendered))
    original_edges = original.filter(ImageFilter.FIND_EDGES)
    edges = ImageChops.difference(original_edges, rendered.filter(ImageFilter.FIND_EDGES))
    # 边缘区域单独归一化，小面积分隔线不再被整幅背景稀释。
    mask = original_edges.point(lambda value: min(255, value * 4))
    detail = ImageStat.Stat(edges, mask).mean[0] ** 2 if mask.getbbox() else 0
    chromatic = ImageChops.difference(reference.filter(ImageFilter.FIND_EDGES),
                                    candidate.filter(ImageFilter.FIND_EDGES))
    return 0.45 * tone + 0.4 * detail + 0.15 * _mean_square(chromatic)


def _mean_square(image):
    stats = ImageStat.Stat(image)
    return sum(stats.sum2) / (image.width * image.height * len(stats.sum2))


def _is_pixel_art(sample):
    if sample.getcolors(64) is None:
        return False
    width, height = sample.size
    pixels = list(sample.get_flattened_data())
    equal = sum(pixels[y * width + x] == pixels[y * width + x - 1] for y in range(height) for x in range(1, width))
    return equal / (height * (width - 1)) >= 0.8
