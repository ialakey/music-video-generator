"""Подписи трека и полоса прогресса в стиле плеера."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import ProgressCfg, TextItemCfg
from ..draw import (Layer, draw_text, load_font, parse_color, text_size,
                    ui_scale, with_alpha)


def format_time(seconds: float) -> str:
    """Секунды -> M:SS (или H:MM:SS для длинных записей)."""
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class _Sprite:
    """Готовая надпись с позицией и параметрами появления."""

    __slots__ = ("image", "pos", "delay", "fade_in", "opacity")

    def __init__(self, image: Image.Image, pos: tuple[int, int],
                 delay: float, fade_in: float, opacity: float) -> None:
        self.image = image
        self.pos = pos
        self.delay = delay
        self.fade_in = fade_in
        self.opacity = opacity

    def alpha_at(self, t: float) -> float:
        if self.fade_in <= 0:
            return self.opacity if t >= self.delay else 0.0
        return self.opacity * float(np.clip((t - self.delay) / self.fade_in, 0.0, 1.0))


class TextLayer:
    """Рендерит надписи один раз и покадрово только меняет прозрачность."""

    def __init__(self, items: list[TextItemCfg], size: tuple[int, int]) -> None:
        self.size = size
        self.scale = ui_scale(size)
        self._sprites = [s for s in (self._build(i) for i in items) if s is not None]

    def _build(self, cfg: TextItemCfg) -> _Sprite | None:
        text = cfg.text.upper() if cfg.uppercase else cfg.text
        if not text.strip():
            return None

        font = load_font(cfg.font, int(round(cfg.size * self.scale)))
        spacing = cfg.letter_spacing * self.scale
        tw, th = text_size(text, font, spacing)
        shadow = max(0.0, cfg.shadow * self.scale)
        pad = int(shadow * 2 + 8)

        canvas = Image.new("RGBA", (tw + pad * 2, th + pad * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        baseline = (pad, pad + th)
        color = with_alpha(parse_color(cfg.color), 1.0)

        if shadow > 0:
            glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            draw_text(ImageDraw.Draw(glow), baseline, text, font,
                      parse_color(cfg.shadow_color), spacing)
            canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(shadow / 2.0)))

        draw_text(draw, baseline, text, font, color, spacing)

        x = int(round(cfg.position[0] * self.size[0]))
        y = int(round(cfg.position[1] * self.size[1]))
        if cfg.align == "center":
            x -= canvas.width // 2
        elif cfg.align == "right":
            x -= canvas.width
        else:
            x -= pad
        y -= pad + th // 2

        return _Sprite(canvas, (x, y), cfg.delay, cfg.fade_in,
                       float(np.clip(cfg.opacity, 0.0, 1.0)))

    def paste(self, frame: Image.Image, t: float) -> None:
        """Накладывает все надписи на кадр (кадр меняется на месте)."""
        for sprite in self._sprites:
            alpha = sprite.alpha_at(t)
            if alpha <= 0.002:
                continue
            img = sprite.image
            if alpha < 0.998:
                img = _scale_alpha(img, alpha)
            frame.alpha_composite(img, sprite.pos)


def _scale_alpha(image: Image.Image, factor: float) -> Image.Image:
    """Копия картинки с умноженным альфа-каналом."""
    out = image.copy()
    a = np.asarray(out.getchannel("A"), dtype=np.float32) * factor
    out.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    return out


class ProgressBar:
    """Полоса воспроизведения с бегунком и таймкодами."""

    def __init__(self, cfg: ProgressCfg, size: tuple[int, int], duration: float) -> None:
        self.cfg = cfg
        self.size = size
        self.duration = max(duration, 1e-6)
        self.enabled = cfg.enabled
        if not self.enabled:
            return

        k = ui_scale(size)
        self.bar_w = cfg.width * size[0]
        self.thickness = max(1.0, cfg.thickness * k)
        self.knob = cfg.knob * k
        self.cx = cfg.position[0] * size[0]
        self.cy = cfg.position[1] * size[1]
        self.x0 = self.cx - self.bar_w / 2.0
        self.x1 = self.cx + self.bar_w / 2.0

        self.color = parse_color(cfg.color)
        self.track = parse_color(cfg.track_color)
        self.font = load_font(None, int(round(cfg.timecode_size * k)))
        self.tc_color = parse_color(cfg.timecode_color)
        self.tc_gap = 18 * k

        pad = int(max(self.knob, self.thickness) * 2 + 6)
        self._bbox = (
            max(0, int(self.x0 - pad)), max(0, int(self.cy - pad)),
            min(size[0], int(self.x1 + pad)), min(size[1], int(self.cy + pad)),
        )

    def paste(self, frame: Image.Image, t: float, alpha: float = 1.0) -> None:
        if not self.enabled or alpha <= 0.002:
            return
        progress = float(np.clip(t / self.duration, 0.0, 1.0))
        x0, y0, x1, y1 = self._bbox
        layer = Layer((x1 - x0, y1 - y0), scale=2, origin=(x0, y0))

        half = self.thickness / 2.0
        layer.rect((self.x0, self.cy - half, self.x1, self.cy + half), self.track, half)
        played = self.x0 + self.bar_w * progress
        if played > self.x0:
            layer.rect((self.x0, self.cy - half, played, self.cy + half), self.color, half)
        if self.knob > 0:
            layer.circle((played, self.cy), self.knob, self.color)

        img = layer.resolve()
        if alpha < 0.998:
            img = _scale_alpha(img, alpha)
        frame.alpha_composite(img, (x0, y0))

        if self.cfg.timecodes:
            self._timecodes(frame, t, alpha)

    def _timecodes(self, frame: Image.Image, t: float, alpha: float) -> None:
        draw = ImageDraw.Draw(frame)
        color = with_alpha(self.tc_color, alpha)
        draw.text((self.x0 - self.tc_gap, self.cy), format_time(t),
                  font=self.font, fill=color, anchor="rm")
        draw.text((self.x1 + self.tc_gap, self.cy), format_time(self.duration),
                  font=self.font, fill=color, anchor="lm")
