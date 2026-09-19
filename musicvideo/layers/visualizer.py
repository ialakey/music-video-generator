"""Визуализатор спектра: радиальные лучи, бары, кольцо, волна, точки."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from ..audio import Analysis, slice_bands
from ..config import VisualizerCfg
from ..draw import Layer, RGBA, gradient_colors, parse_color, ui_scale, with_alpha
from ..i18n import tr

STYLES = ("circle", "bars", "mirror", "wave", "ring", "dots")


class Visualizer:
    """Считает геометрию один раз, а по кадрам только рисует."""

    def __init__(self, cfg: VisualizerCfg, size: tuple[int, int],
                 analysis: Analysis) -> None:
        if cfg.style not in STYLES:
            raise ValueError(
                tr("err.unknown_style", name=cfg.style,
                  available=", ".join(STYLES))
            )
        self.cfg = cfg
        self.size = size
        self.enabled = cfg.enabled

        self.lo, self.hi = slice_bands(analysis, cfg.range)
        self.n = max(2, self.hi - self.lo)

        #: размеры в конфиге заданы для кадра с короткой стороной 1080
        self.k = ui_scale(size)
        self.amp = cfg.amplitude * self.k
        self.radius = cfg.radius * self.k
        self.thickness = max(1.0, cfg.thickness * self.k)
        self.gap = cfg.gap * self.k
        self.center = (cfg.center[0] * size[0], cfg.center[1] * size[1])
        self.baseline = cfg.baseline * size[1]

        base = parse_color(cfg.color)
        second = parse_color(cfg.color2) if cfg.color2 else None
        ramp = gradient_colors(base, second, self.n)
        if self._is_mirrored():
            # зеркалим и палитру, иначе половинки кольца окрашены по-разному
            ramp = ramp + ramp[::-1]
        self.colors: list[RGBA] = [with_alpha(c, cfg.opacity) for c in ramp]
        self._bbox = self._compute_bbox()

    # ------------------------------------------------------------------ #
    def _is_mirrored(self) -> bool:
        return self.cfg.style in ("circle", "ring", "dots") and self.cfg.mirror

    def _compute_bbox(self) -> tuple[int, int, int, int]:
        """Минимальная область кадра, которую затрагивает визуализатор."""
        w, h = self.size
        pad = int(self.thickness * 2 + 4)
        if self.cfg.style in ("circle", "ring", "dots"):
            reach = self.radius + (0 if self.cfg.inward else self.amp) + pad
            cx, cy = self.center
            box = (cx - reach, cy - reach, cx + reach, cy + reach)
        elif self.cfg.style == "mirror":
            box = (0, self.baseline - self.amp - pad, w, self.baseline + self.amp + pad)
        elif self.cfg.style == "wave":
            box = (0, self.baseline - self.amp - pad, w, self.baseline + self.amp + pad)
        else:  # bars
            box = (0, self.baseline - self.amp - pad, w, self.baseline + pad)

        x0 = max(0, int(math.floor(box[0])))
        y0 = max(0, int(math.floor(box[1])))
        x1 = min(w, int(math.ceil(box[2])))
        y1 = min(h, int(math.ceil(box[3])))
        if x1 <= x0 or y1 <= y0:
            return (0, 0, w, h)
        return (x0, y0, x1, y1)

    def _levels(self, analysis: Analysis, index: int) -> np.ndarray:
        return analysis.bands[analysis.clamp(index), self.lo:self.hi]

    # ------------------------------------------------------------------ #
    def render(self, analysis: Analysis, index: int) -> tuple[Image.Image, tuple[int, int]] | None:
        """Возвращает RGBA-слой и координаты его вставки, либо None."""
        if not self.enabled:
            return None
        levels = self._levels(analysis, index)
        x0, y0, x1, y1 = self._bbox
        layer = Layer((x1 - x0, y1 - y0), scale=2, origin=(x0, y0))

        drawer = getattr(self, f"_draw_{self.cfg.style}")
        drawer(layer, levels)

        img = layer.resolve(self.cfg.glow * self.k, self.cfg.glow_strength)
        return img, (x0, y0)

    # ------------------------------------------------------------------ #
    #  Радиальные стили
    # ------------------------------------------------------------------ #
    def _radial_values(self, levels: np.ndarray) -> np.ndarray:
        """Спектр по кругу: при mirror — зеркальная копия для симметрии."""
        if self.cfg.mirror:
            return np.concatenate([levels, levels[::-1]])
        return levels

    def _draw_circle(self, layer: Layer, levels: np.ndarray) -> None:
        values = self._radial_values(levels)
        cx, cy = self.center
        step = 360.0 / len(values)
        sign = -1.0 if self.cfg.inward else 1.0
        round_cap = self.cfg.cap == "round"

        for i, v in enumerate(values):
            angle = math.radians(self.cfg.start_angle + i * step)
            ca, sa = math.cos(angle), math.sin(angle)
            r0 = self.radius
            r1 = self.radius + sign * (self.amp * float(v) + self.thickness * 0.5)
            layer.line(
                (cx + ca * r0, cy + sa * r0),
                (cx + ca * r1, cy + sa * r1),
                self.colors[i], self.thickness, round_cap,
            )

    def _draw_dots(self, layer: Layer, levels: np.ndarray) -> None:
        values = self._radial_values(levels)
        cx, cy = self.center
        step = 360.0 / len(values)
        sign = -1.0 if self.cfg.inward else 1.0

        for i, v in enumerate(values):
            angle = math.radians(self.cfg.start_angle + i * step)
            r = self.radius + sign * self.amp * float(v)
            layer.circle(
                (cx + math.cos(angle) * r, cy + math.sin(angle) * r),
                self.thickness * (0.5 + 0.7 * float(v)),
                self.colors[i],
            )

    def _draw_ring(self, layer: Layer, levels: np.ndarray) -> None:
        """Замкнутая гладкая линия — радиус модулируется спектром."""
        values = self._radial_values(levels)
        cx, cy = self.center
        sign = -1.0 if self.cfg.inward else 1.0
        # сглаживаем стык, чтобы кольцо было непрерывным
        smooth = _wrap_smooth(values, 1.2)
        step = 2.0 * math.pi / len(smooth)

        points = []
        for i, v in enumerate(smooth):
            angle = math.radians(self.cfg.start_angle) + i * step
            r = self.radius + sign * self.amp * float(v)
            points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))

        points.append(points[0])
        for i in range(len(points) - 1):
            layer.line(points[i], points[i + 1],
                       self.colors[min(i, len(self.colors) - 1)], self.thickness)

    # ------------------------------------------------------------------ #
    #  Линейные стили
    # ------------------------------------------------------------------ #
    def _bar_geometry(self) -> tuple[float, float]:
        """Ширина бара и шаг между барами по всей ширине кадра."""
        total = self.size[0]
        pitch = total / self.n
        width = max(1.0, min(self.thickness, pitch - self.gap))
        return width, pitch

    def _draw_bars(self, layer: Layer, levels: np.ndarray) -> None:
        width, pitch = self._bar_geometry()
        radius = width / 2.0 if self.cfg.cap == "round" else 0.0
        for i, v in enumerate(levels):
            x = pitch * (i + 0.5)
            height = max(width, self.amp * float(v))
            layer.rect(
                (x - width / 2.0, self.baseline - height, x + width / 2.0, self.baseline),
                self.colors[i], radius,
            )

    def _draw_mirror(self, layer: Layer, levels: np.ndarray) -> None:
        width, pitch = self._bar_geometry()
        radius = width / 2.0 if self.cfg.cap == "round" else 0.0
        for i, v in enumerate(levels):
            x = pitch * (i + 0.5)
            half = max(width / 2.0, self.amp * float(v) / 2.0)
            layer.rect(
                (x - width / 2.0, self.baseline - half,
                 x + width / 2.0, self.baseline + half),
                self.colors[i], radius,
            )

    def _draw_wave(self, layer: Layer, levels: np.ndarray) -> None:
        """Плавная симметричная линия по ширине кадра."""
        values = _wrap_smooth(np.concatenate([levels[::-1], levels]), 1.6)
        count = len(values)
        step = self.size[0] / (count - 1)

        points = [
            (i * step, self.baseline - (float(v) - 0.5) * self.amp)
            for i, v in enumerate(values)
        ]
        for i in range(len(points) - 1):
            layer.line(points[i], points[i + 1],
                       self.colors[min(i % self.n, len(self.colors) - 1)],
                       self.thickness)


def _wrap_smooth(values: np.ndarray, sigma: float) -> np.ndarray:
    """Циклическое гауссово сглаживание — убирает угловатость кривых."""
    if sigma <= 0 or len(values) < 3:
        return values
    radius = max(1, int(round(sigma * 2.5)))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    padded = np.concatenate([values[-radius:], values, values[:radius]])
    return np.convolve(padded, k, mode="valid")
