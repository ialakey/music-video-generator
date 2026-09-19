"""Готовые визуальные пресеты. Каждый — частичный конфиг поверх умолчаний."""
from __future__ import annotations

from typing import Any

#: "audio edit" — как в референсных роликах: размытый фон, круглая обложка,
#: радиальный визуализатор, зерно, подпись и полоса прогресса.
_AESTHETIC: dict[str, Any] = {
    "audio": {"speed": 0.88, "reverb": 0.35, "bass_boost": 2.0},
    "background": {"blur": 22.0, "brightness": 0.5, "zoom": 1.14, "grain": 0.04},
    "cover": {"enabled": True, "shape": "circle", "size": 440, "beat_scale": 0.03},
    "visualizer": {
        "style": "circle", "radius": 262.0, "amplitude": 150.0,
        "thickness": 6.0, "color": "#ffffff", "color2": "#a78bfa", "glow": 18.0,
    },
    "overlay": {"vignette": 0.6, "beat_flash": 0.05},
}

#: Слоу + реверб, максимально «мягкий» тёплый вид, тонкая волна вместо баров.
_LOFI: dict[str, Any] = {
    "audio": {"speed": 0.85, "reverb": 0.5, "reverb_room": 600, "bass_boost": 1.5},
    "background": {
        "blur": 30.0, "brightness": 0.46, "saturation": 0.9,
        "zoom": 1.10, "beat_zoom": 0.008, "shake": 0.0, "grain": 0.055,
    },
    "cover": {"shape": "rounded", "size": 380, "radius": 38,
              "position": [0.5, 0.36], "beat_scale": 0.015},
    "visualizer": {
        "style": "wave", "baseline": 0.875, "amplitude": 150.0,
        "thickness": 4.0, "color": "#ffd9a0", "color2": "#ff9d6c",
        "glow": 22.0, "opacity": 0.8,
    },
    "text": {
        "title": {"size": 58, "color": "#fff2df", "position": [0.5, 0.60]},
        "artist": {"color": "#fff2dfa0", "position": [0.5, 0.657]},
    },
    "progress": {"position": [0.5, 0.735]},
    "overlay": {
        "vignette": 0.62, "tint": "#ffb36b", "tint_strength": 0.14,
        "scanlines": 0.04,
    },
}

#: Фонк/драйв: агрессивные бары снизу, сильная тряска, красный грейд.
_PHONK: dict[str, Any] = {
    "audio": {"speed": 1.0, "reverb": 0.15, "bass_boost": 5.0},
    "background": {
        "blur": 10.0, "brightness": 0.42, "saturation": 0.75,
        "zoom": 1.2, "beat_zoom": 0.05, "shake": 9.0, "grain": 0.07,
    },
    "cover": {"enabled": False},
    "visualizer": {
        "style": "mirror", "baseline": 0.5, "amplitude": 300.0,
        "thickness": 11.0, "gap": 7.0, "cap": "flat",
        "color": "#ff2d4a", "color2": "#ffffff", "glow": 26.0,
        "glow_strength": 1.0,
    },
    "text": {
        "title": {"size": 80, "uppercase": True, "letter_spacing": 5.0,
                  "position": [0.5, 0.2]},
        "artist": {"position": [0.5, 0.27], "color": "#ff2d4ac0"},
    },
    "progress": {"enabled": False},
    "overlay": {
        "vignette": 0.72, "tint": "#ff1f3d", "tint_strength": 0.18,
        "beat_flash": 0.14, "letterbox": 0.08,
    },
}

#: Минимализм: только обложка, тонкое кольцо и подпись.
_MINIMAL: dict[str, Any] = {
    "background": {
        "blur": 40.0, "brightness": 0.38, "zoom": 1.06,
        "beat_zoom": 0.0, "shake": 0.0, "grain": 0.02, "grain_size": 3,
    },
    "cover": {"shape": "rounded", "radius": 24, "size": 400, "beat_scale": 0.012},
    # кольцо должно проходить снаружи обложки: 400/2*√2 ≈ 283
    "visualizer": {
        "style": "ring", "radius": 320.0, "amplitude": 44.0,
        "thickness": 2.5, "color": "#ffffff", "color2": None,
        "glow": 10.0, "opacity": 0.7,
    },
    "overlay": {"vignette": 0.5, "beat_flash": 0.0},
}

#: Ретро-VHS: полосы, тёплая тонировка, летящие точки вместо баров.
_RETRO: dict[str, Any] = {
    "audio": {"speed": 0.92, "reverb": 0.25},
    "background": {
        "blur": 14.0, "brightness": 0.5, "saturation": 1.25,
        "zoom": 1.16, "grain": 0.10, "grain_size": 3,
    },
    "cover": {"shape": "square", "size": 380},
    "visualizer": {
        "style": "dots", "radius": 310.0, "amplitude": 120.0,
        "thickness": 9.0, "color": "#5ef1ff", "color2": "#ff5ecb", "glow": 24.0,
    },
    "overlay": {
        "vignette": 0.6, "scanlines": 0.16, "letterbox": 0.06,
        "tint": "#3ad0ff", "tint_strength": 0.1,
    },
}

#: Вертикальное видео 9:16 для Shorts / Reels / TikTok.
_SHORTS: dict[str, Any] = {
    "video": {"width": 1080, "height": 1920},
    "audio": {"speed": 0.9, "reverb": 0.3},
    "background": {"blur": 20.0, "brightness": 0.5, "zoom": 1.15},
    "cover": {"size": 520, "position": [0.5, 0.34]},
    # радиус + амплитуда должны укладываться в половину ширины кадра (540)
    "visualizer": {
        "style": "circle", "radius": 320.0, "amplitude": 150.0,
        "thickness": 8.0, "center": [0.5, 0.34],
    },
    "text": {
        "title": {"size": 66, "position": [0.5, 0.63]},
        "artist": {"size": 36, "position": [0.5, 0.672]},
    },
    "progress": {"position": [0.5, 0.75], "width": 0.62},
    "overlay": {"vignette": 0.55},
}

PRESETS: dict[str, dict[str, Any]] = {
    "aesthetic": _AESTHETIC,
    "lofi": _LOFI,
    "phonk": _PHONK,
    "minimal": _MINIMAL,
    "retro": _RETRO,
    "shorts": _SHORTS,
}


def describe(name: str) -> str:
    """Однострочное описание пресета на текущем языке интерфейса."""
    from .i18n import tr

    return tr(f"preset.{name}") if name in PRESETS else ""


def descriptions() -> dict[str, str]:
    """Описания всех пресетов на текущем языке."""
    return {name: describe(name) for name in PRESETS}
