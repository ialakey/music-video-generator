"""Конфигурация генератора: вложенные dataclass'ы + загрузка и слияние JSON."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from .i18n import tr


class ConfigError(Exception):
    """Ошибка в файле конфигурации или в CLI-переопределениях."""


# --------------------------------------------------------------------------- #
#  Секции конфигурации
# --------------------------------------------------------------------------- #
@dataclass
class VideoCfg:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    #: качество x264 (меньше = лучше). 18 почти без потерь, но на зернистой
    #: картинке даёт огромный файл; 21 — разумный баланс для таких роликов
    crf: int = 21
    preset: str = "medium"        # пресет скорости x264
    pixel_format: str = "yuv420p"
    audio_bitrate: str = "320k"


@dataclass
class AudioCfg:
    #: 1.0 = оригинал, 0.85 = классический "slowed + reverb", 1.15 = "sped up"
    speed: float = 1.0
    #: количество реверберации 0..1 (0 = выключено)
    reverb: float = 0.0
    #: длина хвоста реверберации в мс
    reverb_room: int = 480
    #: усиление низких частот в дБ
    bass_boost: float = 0.0
    #: нормализация громкости (loudnorm)
    normalize: bool = True
    #: плавное появление/затухание звука в секундах
    fade_in: float = 1.0
    fade_out: float = 3.0
    #: обрезка исходника (до применения скорости)
    start: float = 0.0
    duration: float | None = None


@dataclass
class AnalysisCfg:
    n_bands: int = 64
    n_fft: int = 4096
    fmin: float = 30.0
    fmax: float = 14000.0
    #: динамический диапазон в дБ, отображаемый на 0..1
    db_range: float = 62.0
    #: скорость нарастания и спада полос (0..1, больше = резче)
    attack: float = 0.55
    decay: float = 0.16
    #: сглаживание соседних полос (в полосах)
    band_blur: float = 0.8
    #: подъём высоких частот, чтобы они не тонули (0..1)
    tilt: float = 0.55


@dataclass
class BackgroundCfg:
    #: путь к картинке, к папке с картинками или список путей
    image: str | list[str] | None = None
    #: процедурный фон, если картинка не задана: "gradient" | "noise" | "solid"
    fallback: str = "gradient"
    colors: list[str] = field(default_factory=lambda: ["#1b1033", "#07070c"])
    blur: float = 18.0            # радиус размытия в px
    brightness: float = 0.55      # затемнение 0..1
    saturation: float = 1.05
    #: медленный зум (Ken Burns): во сколько раз увеличится за весь ролик
    zoom: float = 1.12
    #: панорамирование: dx, dy в долях кадра за весь ролик
    pan: list[float] = field(default_factory=lambda: [0.0, 0.0])
    #: "пульс" фона от баса (доля масштаба)
    beat_zoom: float = 0.018
    #: тряска кадра от баса в px
    shake: float = 3.0
    #: длительность кроссфейда между картинками в секундах
    crossfade: float = 1.5
    #: зернистость плёнки 0..1 — главный фактор размера файла
    grain: float = 0.035
    #: крупность зерна в пикселях; 1 = попиксельный шум (несжимаемый и
    #: заметно раздувающий файл), 2-4 — похоже на плёнку и дешевле для кодека
    grain_size: int = 2


@dataclass
class CoverCfg:
    enabled: bool = True
    #: путь к обложке; None -> берётся первая картинка фона
    image: str | None = None
    size: int = 440               # диаметр/сторона в px при высоте 1080
    shape: str = "circle"         # "circle" | "rounded" | "square"
    radius: int = 36              # скругление для "rounded"
    #: позиция центра в долях кадра
    position: list[float] = field(default_factory=lambda: [0.5, 0.44])
    border: float = 3.0
    border_color: str = "#ffffffcc"
    shadow: float = 42.0
    #: вращение как у винила, оборотов в минуту (0 = выключено)
    spin: float = 0.0
    #: пульсация обложки от баса
    beat_scale: float = 0.03


@dataclass
class VisualizerCfg:
    enabled: bool = True
    #: "circle" | "bars" | "mirror" | "wave" | "ring" | "dots"
    style: str = "circle"
    color: str = "#ffffff"
    #: второй цвет для градиента по полосам (None = однотонный)
    color2: str | None = "#8b5cf6"
    opacity: float = 0.92
    glow: float = 16.0            # радиус свечения (0 = выключено)
    glow_strength: float = 0.85
    #: амплитуда полос в px (при высоте 1080)
    amplitude: float = 190.0
    thickness: float = 7.0        # толщина штриха/бара
    gap: float = 5.0              # зазор между барами
    cap: str = "round"            # "round" | "flat"
    # --- circle / ring / dots ---
    radius: float = 250.0         # базовый радиус кольца
    center: list[float] = field(default_factory=lambda: [0.5, 0.44])
    start_angle: float = -90.0
    mirror: bool = True           # зеркалить спектр по кругу
    inward: bool = False          # рисовать лучи внутрь
    # --- bars / mirror / wave ---
    baseline: float = 0.88        # позиция линии в долях высоты
    #: какие частоты показывать: "full" | "bass" | "mid" | "high"
    range: str = "full"


@dataclass
class TextItemCfg:
    text: str = ""
    font: str | None = None
    size: int = 54
    color: str = "#ffffff"
    opacity: float = 1.0
    position: list[float] = field(default_factory=lambda: [0.5, 0.72])
    align: str = "center"         # "left" | "center" | "right"
    letter_spacing: float = 0.0
    uppercase: bool = False
    shadow: float = 18.0
    shadow_color: str = "#000000b0"
    #: появление: длительность и задержка от начала, секунды
    fade_in: float = 0.8
    delay: float = 0.3


@dataclass
class TextCfg:
    title: TextItemCfg = field(default_factory=lambda: TextItemCfg(
        size=64, position=[0.5, 0.70], letter_spacing=1.5))
    artist: TextItemCfg = field(default_factory=lambda: TextItemCfg(
        size=34, position=[0.5, 0.762], color="#ffffffb0",
        letter_spacing=3.0, uppercase=True, delay=0.5))
    #: произвольные дополнительные подписи
    extra: list[TextItemCfg] = field(default_factory=list)


@dataclass
class ProgressCfg:
    enabled: bool = True
    position: list[float] = field(default_factory=lambda: [0.5, 0.855])
    width: float = 0.42           # длина полосы в долях кадра
    thickness: float = 4.0
    color: str = "#ffffff"
    track_color: str = "#ffffff33"
    knob: float = 7.0
    timecodes: bool = True
    timecode_size: int = 22
    timecode_color: str = "#ffffff99"


@dataclass
class OverlayCfg:
    vignette: float = 0.55        # сила виньетки 0..1
    vignette_size: float = 0.78
    scanlines: float = 0.0        # сила горизонтальных полос 0..1
    letterbox: float = 0.0        # доля высоты под чёрные полосы (0.12 = "кино")
    tint: str | None = None       # цвет тонировки, напр. "#ff5a3c"
    tint_strength: float = 0.0
    beat_flash: float = 0.0       # засветка кадра на бит
    fade_in: float = 1.2          # появление картинки из чёрного
    fade_out: float = 2.5


@dataclass
class Config:
    audio_file: str = ""
    output: str = "output/video.mp4"
    preset: str | None = None
    video: VideoCfg = field(default_factory=VideoCfg)
    audio: AudioCfg = field(default_factory=AudioCfg)
    analysis: AnalysisCfg = field(default_factory=AnalysisCfg)
    background: BackgroundCfg = field(default_factory=BackgroundCfg)
    cover: CoverCfg = field(default_factory=CoverCfg)
    visualizer: VisualizerCfg = field(default_factory=VisualizerCfg)
    text: TextCfg = field(default_factory=TextCfg)
    progress: ProgressCfg = field(default_factory=ProgressCfg)
    overlay: OverlayCfg = field(default_factory=OverlayCfg)
    #: рендерить только первые N секунд (быстрая проверка)
    preview: float | None = None
    workers: int = 0              # 0 = по числу ядер

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# --------------------------------------------------------------------------- #
#  Сборка dataclass из словаря
# --------------------------------------------------------------------------- #
_TYPES: dict[str, type] = {
    "VideoCfg": VideoCfg, "AudioCfg": AudioCfg, "AnalysisCfg": AnalysisCfg,
    "BackgroundCfg": BackgroundCfg, "CoverCfg": CoverCfg,
    "VisualizerCfg": VisualizerCfg, "TextCfg": TextCfg,
    "TextItemCfg": TextItemCfg, "ProgressCfg": ProgressCfg,
    "OverlayCfg": OverlayCfg, "Config": Config,
}


def _resolve(annotation: Any) -> Any:
    """Разбирает аннотацию поля (строковую из-за `from __future__`)."""
    if not isinstance(annotation, str):
        if get_origin(annotation) is Union:
            args = [a for a in get_args(annotation) if a is not type(None)]
            return args[0] if len(args) == 1 else annotation
        return annotation
    a = annotation.strip()
    if a.startswith("list[") and a.endswith("]"):
        return list[_resolve(a[5:-1])]  # type: ignore[misc]
    for part in a.split("|"):
        part = part.strip()
        if part in _TYPES:
            return _TYPES[part]
    return Any


def _build(cls: type, data: Any, path: str = ""):
    """Строит dataclass `cls`, накладывая `data` поверх значений по умолчанию.

    Важно: частичный словарь (например `{"artist": {"text": "Kaleo"}}`) меняет
    только указанные поля и сохраняет остальные умолчания вложенной секции.
    """
    return _apply(cls(), data, path)


def _apply(obj: Any, data: Any, path: str = ""):
    """Рекурсивно записывает значения из `data` в экземпляр dataclass `obj`."""
    if not isinstance(data, dict):
        raise ConfigError(
            tr("err.expected_object", path=path or "config",
              kind=type(data).__name__)
        )

    known = {f.name: f for f in fields(obj)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(
            tr("err.unknown_fields", path=path or "config",
              unknown=sorted(unknown), allowed=", ".join(sorted(known)))
        )

    for name, value in data.items():
        f = known[name]
        tp = _resolve(f.type)
        sub = f"{path}.{name}" if path else name
        current = getattr(obj, name)

        if is_dataclass(tp) and isinstance(value, dict):
            base = current if is_dataclass(current) and not isinstance(current, type) else tp()
            setattr(obj, name, _apply(base, value, sub))
        elif get_origin(tp) is list and get_args(tp) and is_dataclass(get_args(tp)[0]):
            if not isinstance(value, list):
                raise ConfigError(tr("err.expected_list", path=sub))
            item_cls = get_args(tp)[0]
            setattr(obj, name, [
                _apply(item_cls(), v, f"{sub}[{i}]") for i, v in enumerate(value)
            ])
        else:
            setattr(obj, name, value)
    return obj


# --------------------------------------------------------------------------- #
#  Слияние и загрузка
# --------------------------------------------------------------------------- #
def deep_merge(base: dict, override: dict) -> dict:
    """Рекурсивно накладывает `override` на `base`, не меняя аргументы."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(
    path: str | Path | None = None,
    overrides: dict | None = None,
    preset: str | None = None,
) -> Config:
    """Собирает конфиг: умолчания -> пресет -> файл -> CLI-переопределения."""
    from .presets import PRESETS

    file_data: dict[str, Any] = {}
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise ConfigError(tr("err.config_missing", path=p))
        try:
            file_data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigError(tr("err.bad_json", path=p, message=e)) from e
        if not isinstance(file_data, dict):
            raise ConfigError(tr("err.expected_json_object", path=p))

    # пресет может быть задан в файле или в CLI (CLI приоритетнее)
    preset_name = preset or file_data.get("preset")
    data: dict[str, Any] = {}
    if preset_name:
        if preset_name not in PRESETS:
            raise ConfigError(
                tr("err.unknown_preset", name=preset_name,
                  available=", ".join(PRESETS))
            )
        data = deep_merge(data, PRESETS[preset_name])

    data = deep_merge(data, file_data)
    if overrides:
        data = deep_merge(data, overrides)
    if preset_name:
        data["preset"] = preset_name

    return _build(Config, data)
