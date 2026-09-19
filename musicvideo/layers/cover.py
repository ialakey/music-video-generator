"""Обложка трека: круг/скругление/квадрат с рамкой, тенью, пульсом и вращением."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ..config import CoverCfg
from ..draw import fit_cover, parse_color, rounded_mask, ui_scale

#: Во сколько раз базовый спрайт крупнее номинала — запас на пульс без мыла.
_OVERSAMPLE = 1.25


class Cover:
    """Готовит спрайт обложки один раз и наклеивает его на кадр."""

    def __init__(self, cfg: CoverCfg, size: tuple[int, int],
                 image: Path | None = None) -> None:
        self.cfg = cfg
        self.canvas = size
        self.enabled = cfg.enabled

        source = Path(cfg.image).expanduser() if cfg.image else image
        if not self.enabled or source is None or not Path(source).exists():
            self.enabled = False
            return

        scale = ui_scale(size)
        self.base_px = max(16, int(round(cfg.size * scale)))
        self.border_px = max(0.0, cfg.border * scale)
        self.shadow_px = max(0.0, cfg.shadow * scale)
        self.spin = cfg.spin

        self._sprite = self._build_sprite(Path(source))
        self._shadow = self._build_shadow()
        #: кэш масштабированных спрайтов — размер меняется в узком диапазоне
        #: из-за пульса, так что почти каждый кадр попадает в готовый вариант
        self._scaled: dict[int, Image.Image] = {}
        self._scaled_shadow: dict[int, Image.Image] = {}

    # ------------------------------------------------------------------ #
    def _build_sprite(self, path: Path) -> Image.Image:
        """Картинка, обрезанная по форме и с рамкой, в увеличенном разрешении."""
        side = int(self.base_px * _OVERSAMPLE)
        with Image.open(path) as raw:
            img = raw.convert("RGB")
            img.load()
        img = fit_cover(img, (side, side))

        radius = int(round(self.cfg.radius * side / max(self.cfg.size, 1)))
        mask = rounded_mask((side, side), radius, self.cfg.shape)

        sprite = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sprite.paste(img, (0, 0), mask)

        if self.border_px > 0:
            width = max(1, int(round(self.border_px * _OVERSAMPLE)))
            ring = Image.new("RGBA", (side * 4, side * 4), (0, 0, 0, 0))
            d = ImageDraw.Draw(ring)
            box = [width * 2, width * 2, side * 4 - width * 2 - 1, side * 4 - width * 2 - 1]
            color = parse_color(self.cfg.border_color)
            if self.cfg.shape == "circle":
                d.ellipse(box, outline=color, width=width * 4)
            elif self.cfg.shape == "square":
                d.rectangle(box, outline=color, width=width * 4)
            else:
                d.rounded_rectangle(box, radius=radius * 4, outline=color, width=width * 4)
            sprite.alpha_composite(ring.resize((side, side), Image.LANCZOS))

        return sprite

    def _build_shadow(self) -> Image.Image | None:
        """Мягкая тень под обложкой (рисуется один раз)."""
        if self.shadow_px <= 0:
            return None
        pad = int(self.shadow_px * 2)
        side = self._sprite.width
        canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
        solid = Image.new("RGBA", (side, side), (0, 0, 0, 170))
        canvas.paste(solid, (pad, pad), self._sprite.getchannel("A"))
        return canvas.filter(ImageFilter.GaussianBlur(self.shadow_px))

    # ------------------------------------------------------------------ #
    def paste(self, frame: Image.Image, t: float, bass: float) -> None:
        """Рисует обложку на кадре (кадр меняется на месте)."""
        if not self.enabled:
            return

        scale = 1.0 + self.cfg.beat_scale * bass
        side = max(2, int(round(self.base_px * scale)))
        cx = int(round(self.cfg.position[0] * self.canvas[0]))
        cy = int(round(self.cfg.position[1] * self.canvas[1]))

        if self._shadow is not None:
            shadow = self._scaled_shadow.get(side)
            if shadow is None:
                ratio = side / self._sprite.width
                sw = max(2, int(round(self._shadow.width * ratio)))
                shadow = self._shadow.resize((sw, sw), Image.BILINEAR)
                self._scaled_shadow[side] = shadow
            sw = shadow.width
            frame.alpha_composite(shadow, (cx - sw // 2, cy - sw // 2 + int(side * 0.02)))

        if self.spin:
            angle = (t * self.spin / 60.0) * 360.0
            small = self._sprite.rotate(-angle, resample=Image.BICUBIC) \
                                .resize((side, side), Image.LANCZOS)
        else:
            small = self._scaled.get(side)
            if small is None:
                small = self._sprite.resize((side, side), Image.LANCZOS)
                self._scaled[side] = small
        frame.alpha_composite(small, (cx - side // 2, cy - side // 2))

    @property
    def center(self) -> tuple[int, int]:
        return (int(round(self.cfg.position[0] * self.canvas[0])),
                int(round(self.cfg.position[1] * self.canvas[1])))
