"""Проверки логики, не требующие рендера видео.

Запуск:  python -m pytest tests -q      (или  python tests/test_musicvideo.py)
"""
from __future__ import annotations

import os
import string
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from musicvideo import i18n
from musicvideo.audio import analyze, slice_bands
from musicvideo.cli import (build_parser, language_from_argv, normalize_argv,
                            overrides_from_args)
from musicvideo.config import AnalysisCfg, ConfigError, deep_merge, load_config
from musicvideo.draw import gradient_colors, mix, parse_color, ui_scale, with_alpha
from musicvideo.ffmpeg import build_audio_filters
from musicvideo.config import AudioCfg
from musicvideo.i18n import tr
from musicvideo.layers.text import format_time
from musicvideo.presets import describe


# --------------------------------------------------------------------------- #
#  Конфигурация
# --------------------------------------------------------------------------- #
def test_partial_section_keeps_other_defaults():
    """Частичный словарь не должен затирать соседние поля секции."""
    cfg = load_config(None, {"text": {"artist": {"text": "Kaleo"}}})
    assert cfg.text.artist.text == "Kaleo"
    # эти значения заданы в default_factory и должны сохраниться
    assert cfg.text.artist.uppercase is True
    assert cfg.text.artist.position == [0.5, 0.762]
    assert cfg.text.title.size == 64


def test_priority_preset_then_file_then_cli():
    cfg = load_config(None, {"audio": {"speed": 0.7}}, preset="aesthetic")
    assert cfg.audio.speed == 0.7            # CLI перебивает пресет
    assert cfg.audio.reverb == 0.35          # остальное берётся из пресета
    assert cfg.preset == "aesthetic"


def test_unknown_key_is_reported_with_path():
    with pytest.raises(ConfigError) as e:
        load_config(None, {"visualizer": {"colour": "#fff"}})
    assert "visualizer" in str(e.value) and "colour" in str(e.value)


def test_unknown_preset_lists_available():
    with pytest.raises(ConfigError) as e:
        load_config(None, {}, preset="нетакого")
    assert "aesthetic" in str(e.value)


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"x": 1, "y": 2}}
    over = {"a": {"y": 3}}
    out = deep_merge(base, over)
    assert out == {"a": {"x": 1, "y": 3}}
    assert base == {"a": {"x": 1, "y": 2}}


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def test_render_is_the_default_command():
    assert normalize_argv(["track.mp3", "-i", "a.jpg"])[0] == "render"
    assert normalize_argv(["still", "track.mp3"])[0] == "still"
    assert normalize_argv(["--help"])[0] == "--help"


def test_cli_overrides_map_to_config_paths():
    args = build_parser().parse_args(normalize_argv(
        ["t.mp3", "-i", "a.jpg", "-i", "b.jpg", "--speed", "0.85",
         "--style", "bars", "--size", "1080x1920", "--no-cover"]
    ))
    o = overrides_from_args(args)
    assert o["background"]["image"] == ["a.jpg", "b.jpg"]
    assert o["audio"]["speed"] == 0.85
    assert o["visualizer"]["style"] == "bars"
    assert o["video"] == {"width": 1080, "height": 1920}
    assert o["cover"]["enabled"] is False


def test_bad_size_is_rejected():
    args = build_parser().parse_args(normalize_argv(["t.mp3", "--size", "большой"]))
    with pytest.raises(ConfigError):
        overrides_from_args(args)


# --------------------------------------------------------------------------- #
#  Цвета и масштаб
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [
    ("#fff", (255, 255, 255, 255)),
    ("#ff0000", (255, 0, 0, 255)),
    ("#ff000080", (255, 0, 0, 128)),
    ("#f008", (255, 0, 0, 136)),
    ("red", (255, 0, 0, 255)),
])
def test_parse_color(value, expected):
    assert parse_color(value) == expected


def test_parse_color_rejects_garbage():
    with pytest.raises(ValueError):
        parse_color("#12345")


def test_color_helpers():
    assert mix((0, 0, 0, 0), (255, 255, 255, 255), 0.5) == (128, 128, 128, 128)
    assert with_alpha((255, 255, 255, 255), 0.5)[3] == 128
    ramp = gradient_colors((0, 0, 0, 255), (255, 255, 255, 255), 3)
    assert [c[0] for c in ramp] == [0, 128, 255]
    assert gradient_colors((1, 2, 3, 4), None, 5) == [(1, 2, 3, 4)] * 5


def test_ui_scale_matches_for_both_orientations():
    """1920x1080 и 1080x1920 должны давать одинаковый масштаб интерфейса."""
    assert ui_scale((1920, 1080)) == 1.0
    assert ui_scale((1080, 1920)) == 1.0
    assert ui_scale((1280, 720)) == pytest.approx(2 / 3)


# --------------------------------------------------------------------------- #
#  Аудиофильтры
# --------------------------------------------------------------------------- #
def test_speed_becomes_asetrate():
    chain = ",".join(build_audio_filters(AudioCfg(speed=0.85, normalize=False), 44100, 10))
    assert "asetrate=37485" in chain and "aresample=44100" in chain


def test_no_speed_filter_at_normal_speed():
    chain = ",".join(build_audio_filters(AudioCfg(speed=1.0, normalize=False), 44100, 10))
    assert "asetrate" not in chain


def test_reverb_and_fades():
    cfg = AudioCfg(reverb=0.5, fade_in=1.0, fade_out=2.0)
    chain = ",".join(build_audio_filters(cfg, 44100, 30.0))
    assert chain.count("aecho") == 2
    assert "afade=t=in:st=0:d=1.000" in chain
    assert "afade=t=out:st=28.000" in chain


def test_fade_out_skipped_when_track_is_shorter():
    chain = ",".join(build_audio_filters(AudioCfg(fade_out=5.0), 44100, 3.0))
    assert "t=out" not in chain


# --------------------------------------------------------------------------- #
#  Анализ звука
# --------------------------------------------------------------------------- #
def _tone(freq: float, seconds: float = 2.0, sr: int = 44100) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)


def test_analysis_shapes_and_range():
    cfg = AnalysisCfg(n_bands=32, n_fft=2048)
    a = analyze(_tone(440.0), 44100, 30, cfg)
    assert a.bands.shape == (a.n_frames, 32)
    assert a.n_frames == 60
    assert a.bands.min() >= 0.0 and a.bands.max() <= 1.0
    for env in (a.bass, a.mid, a.high, a.level, a.beat):
        assert env.shape == (a.n_frames,)
        assert env.min() >= 0.0 and env.max() <= 1.0


def test_low_tone_lands_in_bass_bands():
    """Чистый бас должен поднимать нижние полосы сильнее верхних."""
    cfg = AnalysisCfg(n_bands=32, n_fft=4096, tilt=0.0)
    a = analyze(_tone(60.0), 44100, 30, cfg)
    peak = int(np.argmax(a.bands.mean(axis=0)))
    assert a.freqs[peak] < 120.0


def test_high_tone_lands_in_high_bands():
    cfg = AnalysisCfg(n_bands=32, n_fft=4096, tilt=0.0)
    a = analyze(_tone(6000.0), 44100, 30, cfg)
    peak = int(np.argmax(a.bands.mean(axis=0)))
    assert a.freqs[peak] > 3000.0


def test_silence_produces_no_movement():
    cfg = AnalysisCfg(n_bands=16, n_fft=2048)
    a = analyze(np.zeros(44100, dtype=np.float32), 44100, 30, cfg)
    assert np.allclose(a.bands, 0.0)
    assert np.allclose(a.beat, 0.0)


def test_frame_count_can_be_forced():
    cfg = AnalysisCfg(n_bands=8, n_fft=1024)
    a = analyze(_tone(440.0, 1.0), 44100, 30, cfg, n_frames=100)
    assert a.n_frames == 100 and a.bands.shape[0] == 100


def test_clamp_keeps_index_in_range():
    cfg = AnalysisCfg(n_bands=8, n_fft=1024)
    a = analyze(_tone(440.0, 0.5), 44100, 30, cfg)
    assert a.clamp(-5) == 0
    assert a.clamp(10 ** 6) == a.n_frames - 1


def test_slice_bands_selects_subranges():
    cfg = AnalysisCfg(n_bands=32, n_fft=2048)
    a = analyze(_tone(440.0, 0.5), 44100, 30, cfg)
    assert slice_bands(a, "full") == (0, 32)
    lo, hi = slice_bands(a, "bass")
    assert lo == 0 and a.freqs[hi - 1] < 250.0
    lo, hi = slice_bands(a, "high")
    assert a.freqs[lo] >= 4000.0


# --------------------------------------------------------------------------- #
#  Мелочи
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seconds,expected", [
    (0, "0:00"), (5, "0:05"), (65, "1:05"), (600, "10:00"), (3725, "1:02:05"),
])
def test_format_time(seconds, expected):
    assert format_time(seconds) == expected


# --------------------------------------------------------------------------- #
#  Язык интерфейса
# --------------------------------------------------------------------------- #
@pytest.fixture
def language():
    """Возвращает язык и переменную окружения в исходное состояние."""
    saved_current = i18n._current
    saved_env = os.environ.get(i18n.ENV_VAR)
    yield i18n.set_language
    i18n._current = saved_current
    if saved_env is None:
        os.environ.pop(i18n.ENV_VAR, None)
    else:
        os.environ[i18n.ENV_VAR] = saved_env


def test_every_message_has_both_languages():
    for key, variants in i18n.MESSAGES.items():
        missing = set(i18n.LANGUAGES) - set(variants)
        assert not missing, f"{key}: нет перевода на {sorted(missing)}"


def test_translations_use_the_same_placeholders():
    """Забытое поле в переводе — это KeyError во время работы, а не косметика."""
    for key, variants in i18n.MESSAGES.items():
        fields = {
            lang: {f for _, f, _, _ in string.Formatter().parse(text) if f}
            for lang, text in variants.items()
        }
        reference = fields[i18n.DEFAULT_LANGUAGE]
        for lang, found in fields.items():
            assert found == reference, f"{key}: {lang} ожидает {found}, а не {reference}"


@pytest.mark.parametrize("value,expected", [
    ("ru", "ru"), ("en", "en"),
    ("ru_RU.UTF-8", "ru"), ("en-US", "en"),
    ("Russian_Russia", "ru"), ("English_United States", "en"),
    ("de", None), ("", None), (None, None),
])
def test_normalize_language(value, expected):
    assert i18n.normalize(value) == expected


def test_translation_switches_with_the_language(language):
    language("en")
    assert tr("err.audio_missing", path="a.mp3") == "Audio file not found: a.mp3"
    language("ru")
    assert tr("err.audio_missing", path="a.mp3") == "Аудиофайл не найден: a.mp3"


def test_unknown_key_returns_itself_instead_of_raising(language):
    language("en")
    assert tr("no.such.key") == "no.such.key"


def test_language_lands_in_the_environment_for_workers(language):
    """Воркеры поднимаются через spawn и берут язык только из окружения."""
    language("ru")
    assert os.environ[i18n.ENV_VAR] == "ru"


def test_unknown_language_falls_back_to_detection(language):
    os.environ[i18n.ENV_VAR] = "en"
    assert language("klingon") == "en"


@pytest.mark.parametrize("argv,expected", [
    (["track.mp3", "--lang", "ru"], "ru"),
    (["track.mp3", "--lang=en"], "en"),
    (["still", "track.mp3", "--lang", "ru", "--at", "30"], "ru"),
    (["track.mp3"], None),
])
def test_language_from_argv(argv, expected):
    assert language_from_argv(argv) == expected


def test_help_follows_the_chosen_language(language):
    language("en")
    assert "render the video" in build_parser().format_help()
    language("ru")
    assert "собрать видео" in build_parser().format_help()


def test_help_headings_are_translated(language):
    language("ru")
    help_text = build_parser().format_help()
    assert help_text.startswith("использование: ")
    assert "позиционные аргументы:" in help_text
    assert "опции:" in help_text


def test_usage_prefix_does_not_leak_into_subcommand_prog(language):
    """argparse собирает prog подкоманды из строки вызова родителя,
    передавая пустой префикс; принять её за «не задан» — значит вписать
    слово «использование» в prog и в текст каждой ошибки."""
    language("ru")
    parser = build_parser()
    render = parser._subparsers._group_actions[0].choices["render"]
    assert render.prog == "musicvideo render"
    assert render.format_usage().count("использование:") == 1


def test_preset_descriptions_follow_the_language(language):
    language("en")
    assert describe("lofi") == "soft warm look, gentle wave, heavy slowdown"
    language("ru")
    assert describe("lofi") == "мягкий тёплый вид, плавная волна, сильный слоу"
    assert describe("nope") == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
