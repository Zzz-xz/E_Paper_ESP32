"""按原图坐标分块采样并保留细线，重叠区只用于滤波而不参与重复拼接。"""
import math

from PIL import Image, ImageChops, ImageFilter

SAMPLE_SCALE = 2
TILE_SIZE = 128
TILE_HALO = 12


def sample_details(source: Image.Image, size: tuple[int, int], box) -> Image.Image:
    """按原图坐标逐块采样到至多 800×600，合并后统一缩小，避免提前缩图丢失细线。"""
    working_size = (size[0] * SAMPLE_SCALE, size[1] * SAMPLE_SCALE)
    working = Image.new("RGB", working_size)
    for center, bounds in _tile_regions(working_size):
        source_box = tuple(box[index % 2] + value * (box[index % 2 + 2] - box[index % 2]) / working_size[index % 2]
                           for index, value in enumerate(bounds))
        tile = _sample_source_tile(source, source_box, (bounds[2] - bounds[0], bounds[3] - bounds[1]))
        _paste_center(working, _enhance_tile(tile), center, bounds)
    # 合并后用面积采样，避免再次引入重采样过冲。
    return working.resize(size, Image.Resampling.BOX)


def _tile_regions(size):
    for top in range(0, size[1], TILE_SIZE):
        for left in range(0, size[0], TILE_SIZE):
            center = (left, top, min(size[0], left + TILE_SIZE), min(size[1], top + TILE_SIZE))
            bounds = (max(0, left - TILE_HALO), max(0, top - TILE_HALO),
                      min(size[0], center[2] + TILE_HALO), min(size[1], center[3] + TILE_HALO))
            yield center, bounds


def _enhance_tile(tile):
    """增强值限制在原邻域颜色范围内，避免锐化产生白色光晕及虚构的高光。"""
    sharpened = tile.filter(ImageFilter.UnsharpMask(radius=1.1, percent=80, threshold=3))
    minimum = tile.filter(ImageFilter.MinFilter(3))
    maximum = tile.filter(ImageFilter.MaxFilter(3))
    return ImageChops.lighter(minimum, ImageChops.darker(maximum, sharpened))


def _sample_source_tile(source, box, size):
    """先裁取源图邻域再缩放，避免每块都触发整张 RGBA 图片的预乘转换。"""
    halo = math.ceil(max((box[2] - box[0]) / size[0], (box[3] - box[1]) / size[1]) * 3)
    bounds = (max(0, math.floor(box[0]) - halo), max(0, math.floor(box[1]) - halo),
              min(source.width, math.ceil(box[2]) + halo), min(source.height, math.ceil(box[3]) + halo))
    local_box = tuple(value - bounds[index % 2] for index, value in enumerate(box))
    return source.crop(bounds).resize(size, Image.Resampling.LANCZOS, box=local_box).convert("RGB")


def _paste_center(image, tile, center, bounds):
    local = (center[0] - bounds[0], center[1] - bounds[1], center[2] - bounds[0], center[3] - bounds[1])
    image.paste(tile.crop(local), center[:2])
