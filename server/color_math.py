"""以双精度数组批量计算三色映射，保留原有明度、色相与细节判定规则。"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Channels:
    rgb: np.ndarray
    hue: np.ndarray
    saturation: np.ndarray
    value: np.ndarray
    luminance: np.ndarray


def analyze(image):
    rgb = np.asarray(image).reshape(-1, 3)
    normalized = rgb.astype(np.float64) / 255
    r, g, b = normalized.T
    maximum = np.max(normalized, axis=1)
    minimum = np.min(normalized, axis=1)
    span = maximum - minimum
    colorful = span != 0
    saturation = np.divide(span, maximum, out=np.zeros_like(span), where=maximum != 0)
    rc = np.divide(maximum - r, span, out=np.zeros_like(span), where=colorful)
    gc = np.divide(maximum - g, span, out=np.zeros_like(span), where=colorful)
    bc = np.divide(maximum - b, span, out=np.zeros_like(span), where=colorful)
    hue = np.where(r == maximum, bc - gc, np.where(g == maximum, 2 + rc - bc, 4 + gc - rc))
    hue = np.where(colorful, (hue / 6) % 1 * 360, 0)
    r, g, b = rgb.T
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return Channels(rgb, hue, saturation, maximum, luminance)


def _context(channels, coverage):
    return np.ones(len(channels.rgb), dtype=bool) if coverage is None else np.asarray(coverage).reshape(-1) != 0


def select_hue(channels, options, coverage=None):
    if options.accent_mode == "manual":
        return options.accent_hue % 360
    if options.accent_mode == "grayscale_red":
        return 0.0
    hues = channels.hue[_context(channels, coverage) & (channels.saturation >= 0.22) & (channels.value >= 0.15)]
    if not len(hues):
        return None
    warm = hues[(hues <= 45) | (hues >= 340)]
    if len(warm) >= max(1, len(hues) / 100):
        red = warm[(warm <= 12) | (warm >= 348)]
        return 0.0 if len(red) >= max(1, len(hues) // 100) else 15.0
    bins = (hues // 30).astype(np.intp)
    counts = np.bincount(bins, minlength=12)
    # 相同频次时沿用原图首次出现的色相，避免数组排序改变重点色。
    dominant = bins[np.flatnonzero(counts[bins] == counts.max())[0]]
    return float(dominant * 30 + 15)


def _distance(hues, selected):
    distance = np.abs(hues - selected) if selected is not None else np.full_like(hues, 360)
    return np.minimum(distance, 360 - distance)


def _histogram(channels, mask):
    return np.bincount(np.rint(channels.luminance[mask]).astype(np.intp), minlength=256).tolist()


def gray_threshold(channels, coverage, selected):
    valid = _context(channels, coverage)
    if selected is not None:
        valid &= ~((channels.saturation >= 0.22) & (_distance(channels.hue, selected) <= 35))
    histogram = _histogram(channels, valid)
    split = _split_histogram(histogram, 18)
    if split is None:
        return 127
    groups = (range(split + 1), range(split + 1, 256))
    means = [sum(value * histogram[value] for value in group) / sum(histogram[value] for value in group) for group in groups]
    return round(sum(means) / 2)


def accent_levels(channels, coverage, selected):
    if selected is None or selected <= 5 or selected >= 355 or 45 < selected < 340:
        return None, None
    mask = _context(channels, coverage) & (channels.saturation >= 0.22) & (_distance(channels.hue, selected) <= 35)
    histogram = _histogram(channels, mask)
    highlight = _split_histogram(histogram, 28)
    shadows = [count if highlight is not None and value <= highlight else 0 for value, count in enumerate(histogram)]
    return _split_histogram(shadows, 14), highlight


def _split_histogram(histogram, minimum_difference):
    total = sum(histogram)
    weighted = sum(value * count for value, count in enumerate(histogram))
    lower_count, lower_sum, best_score, threshold = 0, 0, 0, None
    for value, count in enumerate(histogram):
        lower_count += count
        lower_sum += value * count
        upper_count = total - lower_count
        if min(lower_count, upper_count) < max(1, total * 0.06):
            continue
        difference = (weighted - lower_sum) / upper_count - lower_sum / lower_count
        score = lower_count * upper_count * difference ** 2
        if difference >= minimum_difference and score > best_score:
            best_score, threshold = score, value
    return threshold


def map_colors(channels, selected, options, detail, shadow, highlight):
    lum, saturation, value = channels.luminance, channels.saturation, channels.value
    distance = _distance(channels.hue, selected)
    colored = (selected is not None) & (saturation >= 0.22) & (distance <= 35)
    gray_accent = (options.accent_mode == "grayscale_red") & (lum > 35) & (lum < 225)
    neutral = (selected is not None) & (saturation < 0.22) & (lum > 80) & (lum < 195)
    active = (colored | gray_accent | neutral) & (options.accent_strength > 0)
    gray = np.maximum(0, np.rint(lum - detail))
    result = np.repeat(gray[:, None], 3, axis=1)
    light = np.maximum(0, np.rint(np.where(colored, 0.6 * lum + 0.4 * 255 * value,
                                            255 * (lum / 255) ** 0.65) - detail))
    light = np.where((colored & (value >= 0.25)) | neutral, np.maximum(140, light), light)
    affinity = np.where(colored, 0.45 + 0.55 * saturation * np.maximum(0, 1 - distance / 60), 1)
    other = np.rint(light * (1 - options.accent_strength * affinity))
    result[active] = np.column_stack((light, other, other))[active]
    white = active & colored & (value >= 0.96) & (saturation < 0.65) & (lum > 165)
    pending = active & ~white
    black = pending & (neutral | (colored & ((lum <= highlight) if highlight is not None else True))) & (detail >= 8)
    if shadow is not None:
        black |= pending & colored & (lum - detail <= shadow)
    pending &= ~black
    white |= pending & colored & (lum - detail > (highlight if highlight is not None else 215))
    result[black] = (0, 0, 0)
    result[white] = (255, 255, 255)
    return result.astype(np.uint8)
