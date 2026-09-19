"""Фон: размытая картинка с медленным зумом, пульсом на бит и кроссфейдом."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from ..config import BackgroundCfg
from ..draw import fit_cover, parse_color
from ..i18n import tr

#: Расширения, которые ищем, если указана папка.
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif", ".avif"}


def collect_images(spec: str | list[str] | None) -> list[Path]:
    """Разворачивает путь/папку/список в отсортированный список файлов."""
    if spec is None:
        return []
    items = [spec] if isinstance(spec, str) else list(spec)
    found: list[Path] = []
    for item in items:
        p = Path(item).expanduser()
        if p.is_dir():
            found.extend(sorted(
                c for c in p.iterdir() if c.suffix.lower() in IMAGE_SUFFIXES
            ))
        elif p.exists():
            found.append(p)
        else:
            raise FileNotFoundError(tr("err.background_missing", path=p))
    return found


class Background:
    """Готовит увеличенные кадры-источники и выдаёт кадр фона по времени."""

    def __init__(
        self,
        cfg: BackgroundCfg,
        size: tuple[int, int],
        duration: float,
        extra_images: list[Path] | None = None,
    ) -> None:
        self.cfg = cfg
        self.size = size
        self.duration = max(duration, 1e-6)

        paths = collect_images(cfg.image) or list(extra_images or [])
        #: во сколько раз источник больше кадра — запас на зум, пульс и тряску
        self.max_zoom = max(1.0, cfg.zoom) * (1.0 + max(cfg.beat_zoom, 0.0)) + 0.05
        self.margin = max(cfg.shake, 0.0) * 2.0

        self._sources: list[Image.Image] = [self._prepare(p) for p in paths]
        if not self._sources:
            self._sources = [self._procedural()]

        n = len(self._sources)
        self._segment = self.duration / n if n else self.duration
        self._crossfade = min(max(cfg.crossfade, 0.0), self._segment * 0.5)

    # ------------------------------------------------------------------ #
    #  Подготовка источников
    # ------------------------------------------------------------------ #
    def _source_size(self) -> tuple[int, int]:
        w = int(math.ceil(self.size[0] * self.max_zoom + self.margin))
        h = int(math.ceil(self.size[1] * self.max_zoom + self.margin))
        return w, h

    def _prepare(self, path: Path) -> Image.Image:
        """Масштабирует, размывает и притемняет картинку один раз, не покадрово."""
        with Image.open(path) as raw:
            img = raw.convert("RGB")
            img.load()
        img = fit_cover(img, self._source_size())
        return self._grade(img)

    def _grade(self, img: Image.Image) -> Image.Image:
        cfg = self.cfg
        if cfg.blur > 0:
            img = img.filter(ImageFilter.GaussianBlur(cfg.blur))
        if abs(cfg.saturation - 1.0) > 1e-3:
            img = ImageEnhance.Color(img).enhance(cfg.saturation)
        if abs(cfg.brightness - 1.0) > 1e-3:
            img = ImageEnhance.Brightness(img).enhance(cfg.brightness)
        return img

    def _procedural(self) -> Image.Image:
        """Фон без картинки: градиент, шум или заливка."""
        w, h = self._source_size()
        colors = [parse_color(c) for c in (self.cfg.colors or ["#1b1033", "#07070c"])]
        if len(colors) == 1:
            colors.append(colors[0])
        mode = self.cfg.fallback

        if mode == "solid":
            arr = np.tile(np.array(colors[0][:3], dtype=np.float32), (h, w, 1))
        else:
            # диагональный градиент между заданными цветами
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            t = np.clip((xx / max(w - 1, 1)) * 0.45 + (yy / max(h - 1, 1)) * 0.55, 0, 1)
            stops = np.array([c[:3] for c in colors], dtype=np.float32)
            pos = t * (len(stops) - 1)
            lo = np.floor(pos).astype(np.int32)
            hi = np.minimum(lo + 1, len(stops) - 1)
            frac = (pos - lo)[..., None]
            arr = stops[lo] * (1.0 - frac) + stops[hi] * frac

            if mode == "noise":
                rng = np.random.default_rng(7)
                blob = rng.normal(0, 1, (h // 24 + 2, w // 24 + 2)).astype(np.float32)
                blob_img = Image.fromarray(
                    np.clip(blob * 40 + 128, 0, 255).astype(np.uint8)
                ).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
                arr += (np.asarray(blob_img, dtype=np.float32)[..., None] - 128) * 0.35

        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        return self._grade(img) if mode != "solid" else img

    # ------------------------------------------------------------------ #
    #  Покадровая выдача
    # ------------------------------------------------------------------ #
    def _crop(self, src: Image.Image, t: float, zoom: float,
              shake: tuple[float, float]) -> Image.Image:
        """Вырезает окно нужного масштаба и приводит к размеру кадра."""
        sw, sh = src.size
        w, h = self.size
        # zoom=1 -> видно весь источник; zoom=max_zoom -> масштаб 1:1
        view_w = min(sw, w * self.max_zoom / zoom)
        view_h = min(sh, h * self.max_zoom / zoom)

        progress = t / self.duration
        cx = sw / 2.0 + self.cfg.pan[0] * w * (progress - 0.5) * 2.0 + shake[0]
        cy = sh / 2.0 + self.cfg.pan[1] * h * (progress - 0.5) * 2.0 + shake[1]
        cx = float(np.clip(cx, view_w / 2.0, sw - view_w / 2.0))
        cy = float(np.clip(cy, view_h / 2.0, sh - view_h / 2.0))

        box = (cx - view_w / 2.0, cy - view_h / 2.0,
               cx + view_w / 2.0, cy + view_h / 2.0)
        # картинка уже размыта на этапе подготовки, поэтому BILINEAR
        # неотличим от BICUBIC, но вдвое дешевле на каждом кадре
        return src.resize(self.size, Image.BILINEAR, box=box)

    def frame(self, t: float, bass: float, beat: float, rng: np.random.Generator) -> Image.Image:
        """Кадр фона для момента `t` с учётом баса и удара."""
        cfg = self.cfg
        base = 1.0 + (max(cfg.zoom, 1.0) - 1.0) * (t / self.duration)
        zoom = base * (1.0 + cfg.beat_zoom * bass)
        zoom = float(np.clip(zoom, 1.0, self.max_zoom))

        if cfg.shake > 0 and beat > 0.01:
            amp = cfg.shake * beat
            shake = (float(rng.normal(0, amp * 0.5)), float(rng.normal(0, amp * 0.5)))
        else:
            shake = (0.0, 0.0)

        index, blend, nxt = self._pick(t)
        img = self._crop(self._sources[index], t, zoom, shake)
        if blend > 0:
            other = self._crop(self._sources[nxt], t, zoom, shake)
            img = Image.blend(img, other, blend)
        return img

    def _pick(self, t: float) -> tuple[int, float, int]:
        """Индекс текущей картинки и доля кроссфейда со следующей."""
        n = len(self._sources)
        if n == 1:
            return 0, 0.0, 0
        index = min(int(t / self._segment), n - 1)
        if self._crossfade <= 0 or index >= n - 1:
            return index, 0.0, index
        into_next = t - (index + 1) * self._segment + self._crossfade
        if into_next <= 0:
            return index, 0.0, index
        return index, float(np.clip(into_next / self._crossfade, 0.0, 1.0)), index + 1
