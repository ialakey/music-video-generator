"""Общие утилиты рисования: цвета, шрифты, сглаженные слои, маски."""
from __future__ import annotations

import functools
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .i18n import tr

RGBA = tuple[int, int, int, int]

#: Эталонная короткая сторона кадра. Все размеры в конфиге заданы в пикселях
#: для неё, поэтому 1920x1080 и вертикальное 1080x1920 дают одинаковый масштаб.
REFERENCE_SHORT_SIDE = 1080


def ui_scale(size: tuple[int, int]) -> float:
    """Коэффициент пересчёта размеров интерфейса под текущий кадр."""
    return min(size) / REFERENCE_SHORT_SIDE

#: Куда класть свои .ttf/.otf — они ищутся первыми.
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

#: Предпочитаемые шрифты по убыванию (имя файла без расширения).
_FONT_CANDIDATES = (
    "Montserrat-SemiBold", "Montserrat-Medium", "Poppins-SemiBold",
    "Inter-SemiBold", "Roboto-Medium", "OpenSans-SemiBold",
    "seguisb", "segoeui", "arialbd", "arial",          # Windows
    "HelveticaNeue", "Helvetica",                       # macOS
    "DejaVuSans-Bold", "DejaVuSans", "LiberationSans-Regular",  # Linux
)

_SYSTEM_FONT_DIRS = {
    "win32": [Path("C:/Windows/Fonts")],
    "darwin": [Path("/System/Library/Fonts"), Path("/Library/Fonts"),
               Path.home() / "Library/Fonts"],
}.get(sys.platform, [
    Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
    Path.home() / ".local/share/fonts",
])


# --------------------------------------------------------------------------- #
#  Цвет
# --------------------------------------------------------------------------- #
def parse_color(value: str | None, default: RGBA = (255, 255, 255, 255)) -> RGBA:
    """Разбирает #rgb, #rgba, #rrggbb, #rrggbbaa или имя цвета PIL."""
    if not value:
        return default
    s = value.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        if len(h) != 8:
            raise ValueError(tr("err.bad_color", value=value))
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        except ValueError as e:
            raise ValueError(tr("err.bad_color", value=value)) from e
    from PIL import ImageColor
    try:
        r, g, b = ImageColor.getrgb(s)[:3]
    except ValueError as e:
        raise ValueError(tr("err.unknown_color", value=value)) from e
    return (r, g, b, 255)


def mix(a: RGBA, b: RGBA, t: float) -> RGBA:
    """Линейная интерполяция двух цветов."""
    t = float(np.clip(t, 0.0, 1.0))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))  # type: ignore[return-value]


def with_alpha(color: RGBA, alpha: float) -> RGBA:
    """Умножает альфу цвета на коэффициент 0..1."""
    return (color[0], color[1], color[2],
            int(round(color[3] * float(np.clip(alpha, 0.0, 1.0)))))


def gradient_colors(a: RGBA, b: RGBA | None, count: int) -> list[RGBA]:
    """Готовит `count` цветов между a и b (или сплошной цвет, если b=None)."""
    if b is None or count <= 1:
        return [a] * max(count, 1)
    return [mix(a, b, i / (count - 1)) for i in range(count)]


# --------------------------------------------------------------------------- #
#  Шрифты
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=64)
def _find_font_file(name: str | None) -> str | None:
    """Ищет файл шрифта по явному пути или по списку предпочтений."""
    names = [name] if name else list(_FONT_CANDIDATES)

    for candidate in names:
        if candidate is None:
            continue
        p = Path(candidate)
        if p.suffix and p.exists():
            return str(p)

        stem = p.stem if p.suffix else candidate
        for directory in (FONT_DIR, *_SYSTEM_FONT_DIRS):
            if not directory.exists():
                continue
            for ext in (".ttf", ".otf", ".ttc"):
                exact = directory / f"{stem}{ext}"
                if exact.exists():
                    return str(exact)
            matches = sorted(directory.rglob(f"{stem}*.ttf")) or \
                sorted(directory.rglob(f"{stem}*.otf"))
            if matches:
                return str(matches[0])
    return None


@functools.lru_cache(maxsize=128)
def load_font(name: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Загружает шрифт; при неудаче — встроенный шрифт PIL."""
    size = max(1, int(size))
    path = _find_font_file(name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    if name:  # явно заданный шрифт не нашёлся — пробуем умолчания
        path = _find_font_file(None)
        if path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default(size)


def text_size(
    text: str, font: ImageFont.FreeTypeFont, letter_spacing: float = 0.0
) -> tuple[int, int]:
    """Габариты строки с учётом межбуквенного интервала."""
    if not text:
        return 0, 0
    if letter_spacing <= 0:
        box = font.getbbox(text)
        return box[2] - box[0], box[3] - box[1]
    width = sum(font.getlength(ch) for ch in text) + letter_spacing * (len(text) - 1)
    box = font.getbbox(text)
    return int(round(width)), box[3] - box[1]


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: RGBA,
    letter_spacing: float = 0.0,
    anchor: str = "ls",
) -> None:
    """Рисует строку, поддерживая межбуквенный интервал (PIL его не умеет)."""
    if not text:
        return
    if letter_spacing <= 0:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor=anchor)
        x += font.getlength(ch) + letter_spacing


# --------------------------------------------------------------------------- #
#  Слой со сглаживанием
# --------------------------------------------------------------------------- #
class Layer:
    """RGBA-слой, который рисуется в увеличенном масштабе ради сглаживания.

    PIL не сглаживает примитивы, поэтому рисуем в `scale` раз крупнее
    и уменьшаем результат фильтром LANCZOS.
    """

    def __init__(self, size: tuple[int, int], scale: int = 2,
                 origin: tuple[int, int] = (0, 0)) -> None:
        self.size = size
        self.scale = max(1, int(scale))
        self.origin = origin
        big = (size[0] * self.scale, size[1] * self.scale)
        self.image = Image.new("RGBA", big, (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    # -- координаты пользователя (в пикселях кадра) -> координаты слоя -- #
    def p(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.origin[0]) * self.scale, (y - self.origin[1]) * self.scale)

    def s(self, v: float) -> float:
        return v * self.scale

    def line(self, a: tuple[float, float], b: tuple[float, float],
             color: RGBA, width: float, cap_round: bool = True) -> None:
        pa, pb = self.p(*a), self.p(*b)
        w = max(1, int(round(self.s(width))))
        self.draw.line([pa, pb], fill=color, width=w)
        if cap_round and w > 2:
            r = w / 2.0
            for px, py in (pa, pb):
                self.draw.ellipse([px - r, py - r, px + r, py + r], fill=color)

    def circle(self, center: tuple[float, float], radius: float,
               color: RGBA, width: float = 0) -> None:
        cx, cy = self.p(*center)
        r = self.s(radius)
        box = [cx - r, cy - r, cx + r, cy + r]
        if width > 0:
            self.draw.ellipse(box, outline=color, width=max(1, int(round(self.s(width)))))
        else:
            self.draw.ellipse(box, fill=color)

    def rect(self, box: tuple[float, float, float, float], color: RGBA,
             radius: float = 0.0) -> None:
        x0, y0 = self.p(box[0], box[1])
        x1, y1 = self.p(box[2], box[3])
        if radius > 0:
            self.draw.rounded_rectangle([x0, y0, x1, y1], radius=self.s(radius), fill=color)
        else:
            self.draw.rectangle([x0, y0, x1, y1], fill=color)

    def polygon(self, points: list[tuple[float, float]], color: RGBA) -> None:
        self.draw.polygon([self.p(*pt) for pt in points], fill=color)

    def resolve(self, glow: float = 0.0, glow_strength: float = 0.0) -> Image.Image:
        """Уменьшает слой до целевого размера и добавляет свечение."""
        img = self.image
        if self.scale > 1:
            # для целого коэффициента reduce() — это усреднение по блоку:
            # идеальное сглаживание и заметно быстрее LANCZOS
            img = img.reduce(self.scale)
            if img.size != self.size:
                img = img.resize(self.size, Image.BILINEAR)
        if glow > 0 and glow_strength > 0:
            halo = _glow(img, glow, glow_strength)
            halo.alpha_composite(img)
            img = halo
        return img


#: Во сколько раз уменьшаем слой перед размытием ореола (размытие
#: низкочастотное, поэтому на глаз разницы нет, а считается вчетверо быстрее).
_GLOW_DOWNSCALE = 2


def _glow(img: Image.Image, radius: float, strength: float) -> Image.Image:
    """Мягкий ореол вокруг непрозрачных пикселей.

    Размывать RGBA напрямую нельзя: прозрачные пиксели чёрные, и ореол
    получается грязно-тёмным. Поэтому размываем цвет, умноженный на альфу,
    и делим обратно на размытую альфу.
    """
    full_size = img.size
    factor = _GLOW_DOWNSCALE if radius >= 2 * _GLOW_DOWNSCALE else 1
    work = img.reduce(factor) if factor > 1 else img

    arr = np.asarray(work, dtype=np.float32)
    alpha = arr[..., 3] * np.float32(1.0 / 255.0)
    premul = Image.fromarray(
        np.clip(arr[..., :3] * alpha[..., None], 0, 255).astype(np.uint8), "RGB"
    )
    mask = Image.fromarray((alpha * 255.0).astype(np.uint8), "L")

    blur = ImageFilter.GaussianBlur(radius / factor)
    blurred_rgb = np.asarray(premul.filter(blur), dtype=np.float32)
    blurred_a = np.asarray(mask.filter(blur), dtype=np.float32) * np.float32(1.0 / 255.0)

    rgb = blurred_rgb / np.maximum(blurred_a[..., None], np.float32(1e-3))
    out = np.dstack([
        np.clip(rgb, 0, 255),
        np.clip(blurred_a * np.float32(255.0 * strength), 0, 255),
    ]).astype(np.uint8)

    halo = Image.fromarray(out, "RGBA")
    return halo if halo.size == full_size else halo.resize(full_size, Image.BILINEAR)


# --------------------------------------------------------------------------- #
#  Маски и композитинг
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=8)
def radial_mask(size: tuple[int, int], inner: float, feather: float = 1.0) -> np.ndarray:
    """Радиальный градиент 0..1: 1 в центре, 0 по краям. Для виньетки."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2.0) / (w / 2.0)
    ny = (yy - h / 2.0) / (h / 2.0)
    dist = np.sqrt(nx * nx + ny * ny) / 1.4142135
    t = np.clip((dist - inner) / max(1.0 - inner, 1e-3), 0.0, 1.0)
    return (1.0 - t ** max(feather, 1e-3)).astype(np.float32)


@functools.lru_cache(maxsize=8)
def rounded_mask(size: tuple[int, int], radius: int, shape: str = "rounded",
                 scale: int = 4) -> Image.Image:
    """Мягкая маска формы (круг/скругление/квадрат) в режиме "L"."""
    w, h = size
    big = Image.new("L", (w * scale, h * scale), 0)
    d = ImageDraw.Draw(big)
    if shape == "circle":
        d.ellipse([0, 0, w * scale - 1, h * scale - 1], fill=255)
    elif shape == "square":
        d.rectangle([0, 0, w * scale - 1, h * scale - 1], fill=255)
    else:
        d.rounded_rectangle([0, 0, w * scale - 1, h * scale - 1],
                            radius=radius * scale, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def alpha_over(base: np.ndarray, overlay: Image.Image) -> np.ndarray:
    """Накладывает RGBA-слой на float32-массив кадра (H, W, 3) в 0..255."""
    src = np.asarray(overlay, dtype=np.float32)
    alpha = src[..., 3:4] / 255.0
    return base * (1.0 - alpha) + src[..., :3] * alpha


def fit_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Масштабирует с обрезкой так, чтобы полностью закрыть прямоугольник."""
    w, h = size
    if image.width == 0 or image.height == 0:
        return Image.new("RGB", size, (0, 0, 0))
    scale = max(w / image.width, h / image.height)
    new = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
    resized = image.resize(new, Image.LANCZOS)
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))
