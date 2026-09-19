"""Финальная обработка кадра: виньетка, зерно, полосы, тонировка, фейды."""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..config import OverlayCfg
from ..draw import parse_color, radial_mask

#: Сколько заранее сгенерированных полей шума крутим по кругу.
_GRAIN_TILES = 12


class Overlay:
    """Все полноэкранные эффекты, применяемые к готовому кадру."""

    def __init__(self, cfg: OverlayCfg, size: tuple[int, int], duration: float,
                 grain: float = 0.0, grain_size: int = 2, seed: int = 0) -> None:
        self.cfg = cfg
        self.size = size
        self.duration = max(duration, 1e-6)
        self.grain = max(0.0, float(grain))

        w, h = size
        self._vignette = None
        if cfg.vignette > 0:
            mask = radial_mask(size, float(np.clip(cfg.vignette_size, 0.05, 0.99)), 1.6)
            self._vignette = (1.0 - (1.0 - mask) * float(np.clip(cfg.vignette, 0, 1)))
            self._vignette = self._vignette[..., None].astype(np.float32)

        self._scanlines = None
        if cfg.scanlines > 0:
            rows = np.arange(h, dtype=np.float32)
            wave = 0.5 + 0.5 * np.cos(rows * np.pi)  # чередование строк
            strength = float(np.clip(cfg.scanlines, 0.0, 1.0))
            self._scanlines = (1.0 - wave * strength)[:, None, None].astype(np.float32)

        self._tint = None
        if cfg.tint and cfg.tint_strength > 0:
            rgb = np.array(parse_color(cfg.tint)[:3], dtype=np.float32)
            self._tint = (rgb, float(np.clip(cfg.tint_strength, 0.0, 1.0)))

        self._letterbox = None
        if cfg.letterbox > 0:
            bar = int(round(h * float(np.clip(cfg.letterbox, 0.0, 0.45))))
            if bar > 0:
                self._letterbox = bar

        # Зерно: готовые поля шума в int8 (float32 занял бы сотни МБ на воркер).
        # Шум генерируется в уменьшенном масштабе и растягивается: так он больше
        # похож на плёночное зерно и, главное, в разы дешевле для кодека —
        # попиксельный белый шум несжимаем и раздувает файл в несколько раз.
        self._grain_tiles: list[np.ndarray] = []
        if self.grain > 0:
            rng = np.random.default_rng(seed or 20240917)
            step = max(1, int(grain_size))
            small = (max(2, h // step), max(2, w // step))
            for _ in range(_GRAIN_TILES):
                noise = rng.normal(0.0, 64.0, small)
                patch = Image.fromarray(
                    np.clip(noise + 128.0, 0, 255).astype(np.uint8), "L"
                )
                if step > 1:
                    patch = patch.resize((w, h), Image.BILINEAR)
                field = np.asarray(patch, dtype=np.int16) - 128
                self._grain_tiles.append(
                    np.clip(field, -127, 127).astype(np.int8)[..., None]
                )

    # ------------------------------------------------------------------ #
    def apply(self, frame: np.ndarray, t: float, index: int, beat: float) -> np.ndarray:
        """Применяет эффекты к float32-кадру (H, W, 3) в 0..255.

        Массив меняется на месте: он и так свежая копия из кадра, а лишние
        временные буферы на 1080p стоят заметного времени.
        """
        cfg = self.cfg

        if self._tint is not None:
            rgb, strength = self._tint
            luma = frame @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
            frame *= np.float32(1.0 - strength)
            frame += (luma[..., None] * np.float32(strength / 255.0)) * rgb

        if self._vignette is not None:
            frame *= self._vignette

        if cfg.beat_flash > 0 and beat > 0.01:
            frame += np.float32(255.0 * cfg.beat_flash * beat)

        if self._scanlines is not None:
            frame *= self._scanlines

        if self._grain_tiles:
            noise = self._grain_tiles[index % len(self._grain_tiles)]
            frame += noise * np.float32(self.grain * 3.0)

        fade = self._fade(t)
        if fade < 0.999:
            frame *= np.float32(fade)

        if self._letterbox:
            bar = self._letterbox
            frame[:bar] = 0.0
            frame[-bar:] = 0.0

        return frame

    def _fade(self, t: float) -> float:
        cfg = self.cfg
        value = 1.0
        if cfg.fade_in > 0:
            value = min(value, t / cfg.fade_in)
        if cfg.fade_out > 0:
            remain = self.duration - t
            value = min(value, remain / cfg.fade_out)
        return float(np.clip(value, 0.0, 1.0))
