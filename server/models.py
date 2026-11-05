from typing import Literal
from ipaddress import IPv4Address
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

WIDTH = 400
HEIGHT = 300
PLANE_BYTES = WIDTH * HEIGHT // 8
FRAME_BYTES = PLANE_BYTES * 2
COOLDOWN_SECONDS = 30
DISPLAY_READ_COOLDOWN_SECONDS = 5


class RenderOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    fit: Literal["contain", "cover"] = "contain"
    rotation: Literal[0, 90, 180, 270] = 0
    resample: Literal["smooth", "pixel"] = "smooth"
    brightness: float = Field(default=1, ge=0.5, le=1.5)
    contrast: float = Field(default=1, ge=0.5, le=1.5)
    accent_mode: Literal["auto", "manual", "grayscale_red"] = "auto"
    accent_hue: float = Field(default=0, ge=0, le=360)
    accent_strength: float = Field(default=0.85, ge=0, le=1)
    dither: bool = False


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=1, max_length=64)


class DeviceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["refreshing", "completed", "failed"]
    error: str = Field(default="", max_length=160)


class CanvasBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(default=0, ge=0, lt=WIDTH)
    y: int = Field(default=0, ge=0, lt=HEIGHT)
    width: int = Field(default=WIDTH, ge=1, le=WIDTH)
    height: int = Field(default=HEIGHT, ge=1, le=HEIGHT)

    @model_validator(mode="after")
    def inside_screen(self):
        if self.x + self.width > WIDTH or self.y + self.height > HEIGHT:
            raise ValueError("元素必须位于 400×300 屏幕区域内。")
        return self


class ImageLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_id: str = Field(min_length=1, max_length=64)
    box: CanvasBox = Field(default_factory=CanvasBox)
    options: RenderOptions = Field(default_factory=RenderOptions)
    zoom: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)
    offset_x: float = Field(default=0, ge=-3, le=3, allow_inf_nan=False)
    offset_y: float = Field(default=0, ge=-3, le=3, allow_inf_nan=False)
    recommendation: Literal["auto", "manual"] = "manual"


class TextLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(default="", max_length=500)
    box: CanvasBox = Field(default_factory=CanvasBox)
    font_size: int = Field(default=24, ge=8, le=72)
    color: Literal["foreground", "black", "white", "red"] = "foreground"
    align: Literal["left", "center", "right"] = "left"
    vertical_align: Literal["top", "middle", "bottom"] = "top"
    auto_size: bool = False


class DisplayDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)
    image: ImageLayer | None = None
    texts: list[TextLayer] = Field(default_factory=list, max_length=12)
    foreground: Literal["black", "white", "red"] = "black"
    background: Literal["black", "white", "red"] = "white"

    @model_validator(mode="after")
    def distinct_inks(self):
        if self.foreground == self.background:
            raise ValueError("前景色与背景色不能相同。")
        return self

    @model_validator(mode="after")
    def unique_text_ids(self):
        ids = [item.id for item in self.texts]
        if len(set(ids)) != len(ids) or "image" in ids:
            raise ValueError("文字标识必须唯一，且不能使用 image。")
        return self


def _validate_setup_url(value):
    if not value:
        return value
    parts = urlsplit(value)
    if parts.scheme != "http" or parts.username or parts.password or parts.port not in (None, 80) or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("配网页地址必须为设备的 HTTP IPv4 地址。")
    IPv4Address(parts.hostname)
    return value


class DeviceHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    setup_supported: bool = False
    setup_url: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def validate_url(self):
        _validate_setup_url(self.setup_url)
        return self


class SetupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(default="", max_length=80)
    error: str = Field(default="", max_length=160)
    token: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$", max_length=32)

    @model_validator(mode="after")
    def validate_result(self):
        _validate_setup_url(self.url)
        if not self.url and not self.error:
            raise ValueError("须回报配网页地址或失败原因。")
        if self.url and not self.error and not self.token:
            raise ValueError("成功回报须包含临时配网授权。")
        return self


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=8, max_length=32)


class NewAdminPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(min_length=8, max_length=32)
