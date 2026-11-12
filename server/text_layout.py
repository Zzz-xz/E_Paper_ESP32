"""统一文字测量与栅格化；文字可叠在图片上，图片框不参与自动调整。"""
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import CanvasBox, HEIGHT, WIDTH
from .rendering import BLACK, RED, WHITE

FONT_PATH = Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKsc-Regular.otf"
INKS = {"black": BLACK, "white": WHITE, "red": RED}


@lru_cache(maxsize=8)
def _font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def fit_text_boxes(document):
    texts = list(document.texts)
    for index, text in enumerate(texts):
        if text.auto_size:
            occupied = [item.box for other, item in enumerate(texts) if other != index]
            texts[index] = _fit_text(text, _free_regions(occupied))
    return document.model_copy(update={"texts": texts})


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _free_regions(boxes):
    regions = [(0, 0, WIDTH, HEIGHT)]
    for box in boxes:
        x1, y1, x2, y2 = box.x, box.y, box.x + box.width, box.y + box.height
        candidates = []
        for left, top, right, bottom in regions:
            if left >= x2 or right <= x1 or top >= y2 or bottom <= y1:
                candidates.append((left, top, right, bottom))
            else:
                candidates.extend(((left, top, right, min(bottom, y1)),
                                   (left, max(top, y2), right, bottom),
                                   (left, top, min(right, x1), bottom),
                                   (max(left, x2), top, right, bottom)))
        ordered = sorted({rect for rect in candidates if rect[0] < rect[2] and rect[1] < rect[3]},
                         key=lambda rect: (-(rect[2] - rect[0]) * (rect[3] - rect[1]), rect))
        regions = []
        for rect in ordered:
            if not any(_contains(existing, rect) for existing in regions):
                regions.append(rect)
    return regions


def _fit_text(layer, regions):
    draw = ImageDraw.Draw(Image.new("1", (1, 1)))
    font = _font(layer.font_size)
    paragraphs = layer.text.replace("\r\n", "\n").split("\n")
    natural_width = math.ceil(max(_line_width(line, draw, font, True) for line in paragraphs)) + 2
    candidates, measurements = [], {}
    for left, top, right, bottom in regions:
        width = min(right - left, max(layer.box.width, natural_width))
        if width <= 2:
            continue
        if width not in measurements:
            lines = _wrap(layer.text, width - 2, draw, font, True)
            fits_width = all(_line_width(line, draw, font, True) <= width - 2 for line in lines)
            measurements[width] = (_needed_height(lines, layer.font_size, draw, font) + 2) if fits_width else None
        measured = measurements[width]
        if measured is None:
            continue
        height = max(layer.box.height, measured)
        if height > bottom - top:
            continue
        x = max(left, min(layer.box.x, right - width))
        y = max(top, min(layer.box.y, bottom - height))
        box = CanvasBox(x=x, y=y, width=width, height=height)
        cost = ((x - layer.box.x) ** 2 + (y - layer.box.y) ** 2, width * height)
        candidates.append((cost, box))
    if not candidates:
        raise ValueError(f"文字「{layer.text[:12]}」无法完整放入屏幕区域，请缩小字号、精简文字或调整其他文字框。")
    return layer.model_copy(update={"box": min(candidates, key=lambda value: value[0])[1]})


def text_tile(layer, foreground="black"):
    mask = Image.new("1", (layer.box.width, layer.box.height))
    draw = ImageDraw.Draw(mask)
    font = _font(layer.font_size)
    padding = 1 if layer.auto_size else 0
    lines = _wrap(layer.text, layer.box.width - padding * 2, draw, font, layer.auto_size)
    needed_height = _needed_height(lines, layer.font_size, draw, font)
    remaining = max(0, layer.box.height - padding * 2 - needed_height)
    offset = padding + {"top": 0, "middle": remaining // 2, "bottom": remaining}[layer.vertical_align]
    for index, line in enumerate(lines):
        width = _line_width(line, draw, font, layer.auto_size)
        x = padding + (0 if layer.align == "left" else (layer.box.width - padding * 2 - width) / (2 if layer.align == "center" else 1))
        if layer.auto_size:
            x -= min(0, draw.textbbox((0, 0), line, font=font, anchor="lt")[0])
        draw.text((x, offset + index * round(layer.font_size * 1.35)), line, font=font, fill=1, anchor="lt")
    result = Image.new("RGBA", mask.size, INKS[foreground if layer.color == "foreground" else layer.color] + (255,))
    result.putalpha(mask.convert("L"))
    return result, needed_height > layer.box.height - padding * 2


def _needed_height(lines, size, draw, font):
    return max(index * round(size * 1.35) + draw.textbbox((0, 0), line, font=font, anchor="lt")[3]
               for index, line in enumerate(lines))


def _line_width(line, draw, font, ink=False):
    advance = draw.textlength(line, font=font)
    if not ink:
        return advance
    left, _, right, _ = draw.textbbox((0, 0), line, font=font, anchor="lt")
    return max(advance, right) - min(0, left)


def _wrap(text, width, draw, font, ink=False):
    lines = []
    for paragraph in text.replace("\r\n", "\n").split("\n"):
        line = ""
        for char in paragraph:
            if line and _line_width(line + char, draw, font, ink) > width:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return lines
