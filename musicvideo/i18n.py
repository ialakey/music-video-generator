"""Двуязычные сообщения интерфейса: английский и русский.

Язык выбирается один раз при старте (`--lang`, `MUSICVIDEO_LANG` или локаль
системы) и попадает в переменную окружения, поэтому процессы-воркеры,
поднятые через spawn, наследуют его сами.
"""
from __future__ import annotations

import locale
import os

#: Поддерживаемые языки. Первый — язык по умолчанию и язык запасного варианта.
LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"

#: Переменная окружения; она же передаёт язык процессам-воркерам.
ENV_VAR = "MUSICVIDEO_LANG"

_current: str | None = None


# --------------------------------------------------------------------------- #
#  Каталог
# --------------------------------------------------------------------------- #
#: key -> {язык: строка}. Плейсхолдеры именованные, формат `str.format`.
MESSAGES: dict[str, dict[str, str]] = {
    # --- описание программы и подкоманды -------------------------------- #
    "cli.description": {
        "en": "A generator of YouTube-style audio edit videos: zooming "
              "background, cover art, spectrum visualizer, grain and captions.",
        "ru": "Генератор музыкальных видео в стиле YouTube audio edit: "
              "фон с зумом, обложка, визуализатор спектра, зерно и подписи.",
    },
    "cli.cmd.render": {
        "en": "render the video (the default)",
        "ru": "собрать видео (по умолчанию)",
    },
    "cli.cmd.still": {
        "en": "save a single frame as PNG to check the settings",
        "ru": "сохранить один кадр в PNG для примерки",
    },
    "cli.cmd.presets": {
        "en": "list the available presets",
        "ru": "показать список пресетов",
    },
    "cli.cmd.dump": {
        "en": "write the resolved config as JSON",
        "ru": "выгрузить итоговый конфиг в JSON",
    },

    # --- аргументы ------------------------------------------------------- #
    "cli.arg.at": {
        "en": "frame position in seconds (default: 25%% of the track)",
        "ru": "момент кадра в секундах (по умолчанию 25%% трека)",
    },
    "cli.arg.dump_to": {
        "en": "where to write the JSON ('-' = stdout)",
        "ru": "куда записать JSON ('-' = stdout)",
    },
    "cli.arg.audio": {
        "en": "path to the audio file (mp3/wav/flac/m4a...)",
        "ru": "путь к аудиофайлу (mp3/wav/flac/m4a...)",
    },
    "cli.arg.image": {
        "en": "background image, a folder of images, or the flag repeated",
        "ru": "картинка фона, папка с картинками или флаг несколько раз",
    },
    "cli.arg.output": {
        "en": "where to save the video",
        "ru": "куда сохранить видео",
    },
    "cli.arg.config": {
        "en": "JSON settings file",
        "ru": "JSON-файл настроек",
    },
    "cli.arg.preset": {
        "en": "visual preset",
        "ru": "визуальный пресет",
    },
    "cli.arg.lang": {
        "en": "interface language (default: from MUSICVIDEO_LANG or the system locale)",
        "ru": "язык интерфейса (по умолчанию: из MUSICVIDEO_LANG или локали системы)",
    },
    "cli.arg.title": {
        "en": "track title",
        "ru": "название трека",
    },
    "cli.arg.artist": {
        "en": "artist",
        "ru": "исполнитель",
    },
    "cli.arg.cover": {
        "en": "cover art image",
        "ru": "картинка обложки",
    },
    "cli.arg.no_cover": {
        "en": "draw no cover art",
        "ru": "убрать обложку",
    },
    "cli.arg.style": {
        "en": "visualizer style",
        "ru": "стиль визуализатора",
    },
    "cli.arg.color": {
        "en": "main visualizer color",
        "ru": "основной цвет визуализатора",
    },
    "cli.arg.color2": {
        "en": "second gradient color",
        "ru": "второй цвет градиента",
    },
    "cli.arg.no_visualizer": {
        "en": "draw no visualizer",
        "ru": "убрать визуализатор",
    },
    "cli.arg.no_progress": {
        "en": "draw no progress bar",
        "ru": "убрать полосу прогресса",
    },
    "cli.arg.grain": {
        "en": "film grain; 0 turns it off (shrinks the file a lot)",
        "ru": "плёночное зерно; 0 — выключить (сильно уменьшает файл)",
    },
    "cli.arg.speed": {
        "en": "audio speed: 0.85 = slowed, 1.2 = sped up",
        "ru": "скорость звука: 0.85 = slowed, 1.2 = sped up",
    },
    "cli.arg.reverb": {
        "en": "reverb amount",
        "ru": "количество реверберации",
    },
    "cli.arg.bass": {
        "en": "low-frequency boost",
        "ru": "усиление низких частот",
    },
    "cli.arg.start": {
        "en": "start of the excerpt, seconds",
        "ru": "начало отрезка, сек",
    },
    "cli.arg.length": {
        "en": "length of the excerpt, seconds",
        "ru": "длина отрезка, сек",
    },
    "cli.arg.size": {
        "en": "resolution, e.g. 1920x1080 or 1080x1920",
        "ru": "разрешение, например 1920x1080 или 1080x1920",
    },
    "cli.arg.fps": {
        "en": "frames per second",
        "ru": "кадров в секунду",
    },
    "cli.arg.crf": {
        "en": "x264 quality (lower = better)",
        "ru": "качество x264 (меньше = лучше)",
    },
    "cli.arg.preview": {
        "en": "render only the first SEC seconds",
        "ru": "отрендерить только первые SEC секунд",
    },
    "cli.arg.workers": {
        "en": "number of render processes (1 = no parallelism)",
        "ru": "число процессов рендера (1 = без параллелизма)",
    },
    "cli.arg.quiet": {
        "en": "no progress bar and no messages",
        "ru": "без прогресса и сообщений",
    },

    # --- заголовки справки ------------------------------------------------ #
    # argparse печатает их сам и переводов, кроме английского, не содержит,
    # поэтому мы подставляем свои.
    "cli.help.usage": {
        "en": "usage: ",
        "ru": "использование: ",
    },
    "cli.help.positionals": {
        "en": "positional arguments",
        "ru": "позиционные аргументы",
    },
    "cli.help.options": {
        "en": "options",
        "ru": "опции",
    },
    "cli.help.help": {
        "en": "show this help message and exit",
        "ru": "показать эту справку и выйти",
    },

    # --- эпилог ---------------------------------------------------------- #
    "cli.epilog.presets": {
        "en": "Presets:",
        "ru": "Пресеты:",
    },
    "cli.epilog.examples": {
        "en": "Examples:",
        "ru": "Примеры:",
    },

    # --- ход работы ------------------------------------------------------ #
    "cli.progress.unit": {
        "en": "fps",
        "ru": "кадр/с",
    },
    "cli.progress.eta": {
        "en": "left",
        "ru": "осталось",
    },
    "log.audio": {
        "en": "Processing audio...",
        "ru": "Обрабатываю звук...",
    },
    "log.analysis": {
        "en": "Analyzing the spectrum...",
        "ru": "Анализирую спектр...",
    },
    "log.render": {
        "en": "Rendering: {frames} frames, {width}x{height} @ {fps} fps, "
              "workers: {workers}",
        "ru": "Рендер: {frames} кадров, {width}x{height} @ {fps} fps, "
              "воркеров: {workers}",
    },
    "cli.done": {
        "en": "Done: {path}",
        "ru": "Готово: {path}",
    },
    "cli.done.video": {
        "en": "Done: {path}  ({size:.1f} MB, {elapsed})",
        "ru": "Готово: {path}  ({size:.1f} МБ, {elapsed})",
    },
    "cli.config.written": {
        "en": "Config written: {path}",
        "ru": "Конфиг записан: {path}",
    },
    "cli.interrupted": {
        "en": "Interrupted by the user.",
        "ru": "Прервано пользователем.",
    },

    # --- ошибки ---------------------------------------------------------- #
    "err.prefix.config": {
        "en": "Configuration error: {message}",
        "ru": "Ошибка конфигурации: {message}",
    },
    "err.prefix.generic": {
        "en": "Error: {message}",
        "ru": "Ошибка: {message}",
    },
    "err.no_audio": {
        "en": "no audio file given (positional argument, or audio_file in the config)",
        "ru": "не указан аудиофайл (позиционный аргумент или audio_file в конфиге)",
    },
    "err.bad_size": {
        "en": "--size must look like 1920x1080, got '{value}'",
        "ru": "--size должен быть вида 1920x1080, получено '{value}'",
    },
    "err.bad_lang": {
        "en": "unknown language '{value}'. Available: {available}",
        "ru": "неизвестный язык '{value}'. Доступные: {available}",
    },

    # config.py
    "err.expected_object": {
        "en": "{path}: expected an object, got {kind}",
        "ru": "{path}: ожидался объект, получено {kind}",
    },
    "err.unknown_fields": {
        "en": "{path}: unknown parameters {unknown}.\n  Allowed: {allowed}",
        "ru": "{path}: неизвестные параметры {unknown}.\n  Допустимые: {allowed}",
    },
    "err.expected_list": {
        "en": "{path}: expected a list",
        "ru": "{path}: ожидался список",
    },
    "err.config_missing": {
        "en": "Configuration file not found: {path}",
        "ru": "Файл конфигурации не найден: {path}",
    },
    "err.bad_json": {
        "en": "{path}: malformed JSON — {message}",
        "ru": "{path}: некорректный JSON — {message}",
    },
    "err.expected_json_object": {
        "en": "{path}: expected a JSON object",
        "ru": "{path}: ожидался JSON-объект",
    },
    "err.unknown_preset": {
        "en": "Unknown preset '{name}'. Available: {available}",
        "ru": "Неизвестный пресет '{name}'. Доступные: {available}",
    },

    # draw.py
    "err.bad_color": {
        "en": "Malformed color: {value}",
        "ru": "Некорректный цвет: {value}",
    },
    "err.unknown_color": {
        "en": "Unknown color: {value}",
        "ru": "Неизвестный цвет: {value}",
    },

    # ffmpeg.py
    "err.tool_missing": {
        "en": "{name} not found. Install ffmpeg and add it to PATH.\n"
              "  Windows: winget install Gyan.FFmpeg\n"
              "  macOS:   brew install ffmpeg\n"
              "  Linux:   sudo apt install ffmpeg",
        "ru": "Не найден {name}. Установите ffmpeg и добавьте его в PATH.\n"
              "  Windows: winget install Gyan.FFmpeg\n"
              "  macOS:   brew install ffmpeg\n"
              "  Linux:   sudo apt install ffmpeg",
    },
    "err.tool_failed": {
        "en": "{tool} exited with code {code}:\n  {details}",
        "ru": "{tool} завершился с кодом {code}:\n  {details}",
    },
    "err.audio_missing": {
        "en": "Audio file not found: {path}",
        "ru": "Аудиофайл не найден: {path}",
    },
    "err.no_audio_stream": {
        "en": "The file has no audio stream: {path}",
        "ru": "В файле нет аудиопотока: {path}",
    },
    "err.no_duration": {
        "en": "Could not determine the duration: {path}",
        "ru": "Не удалось определить длительность: {path}",
    },
    "err.empty_span": {
        "en": "Empty excerpt: start={start}s for a duration of {duration:.1f}s",
        "ru": "Пустой отрезок: start={start}s при длительности {duration:.1f}s",
    },
    "err.decode_failed": {
        "en": "Could not decode the audio:\n  {details}",
        "ru": "Не удалось декодировать звук:\n  {details}",
    },
    "err.pipe_closed": {
        "en": "ffmpeg closed the stream: {message}",
        "ru": "ffmpeg закрыл поток: {message}",
    },
    "err.encode_failed": {
        "en": "Encoding failed (code {code}):\n  {details}",
        "ru": "Кодирование не удалось (код {code}):\n  {details}",
    },

    # render.py / layers
    "err.background_missing": {
        "en": "Background image not found: {path}",
        "ru": "Картинка фона не найдена: {path}",
    },
    "err.cover_missing": {
        "en": "Cover art not found: {path}",
        "ru": "Обложка не найдена: {path}",
    },
    "err.unknown_style": {
        "en": "Unknown visualizer style '{name}'. Available: {available}",
        "ru": "Неизвестный стиль визуализатора '{name}'. Доступные: {available}",
    },
    "err.frame_too_small": {
        "en": "Frame is too small: {width}x{height}",
        "ru": "Слишком маленький кадр: {width}x{height}",
    },
    "err.odd_size": {
        "en": "Width and height must be even for {pixel_format}: got {width}x{height}",
        "ru": "Ширина и высота должны быть чётными для {pixel_format}: "
              "получено {width}x{height}",
    },
    "err.bad_fps": {
        "en": "fps must be positive, got {value}",
        "ru": "fps должен быть положительным, получено {value}",
    },
    "err.bad_speed": {
        "en": "speed must be greater than zero, got {value}",
        "ru": "speed должен быть больше нуля, получено {value}",
    },

    # --- пресеты --------------------------------------------------------- #
    "preset.aesthetic": {
        "en": "slowed + reverb, round cover and radial spectrum (like the reference)",
        "ru": "slowed + reverb, круглая обложка и радиальный спектр (как в референсе)",
    },
    "preset.lofi": {
        "en": "soft warm look, gentle wave, heavy slowdown",
        "ru": "мягкий тёплый вид, плавная волна, сильный слоу",
    },
    "preset.phonk": {
        "en": "aggressive mirrored bars, shake, red grade",
        "ru": "агрессивные зеркальные бары, тряска, красный грейд",
    },
    "preset.minimal": {
        "en": "a thin ring around the cover, nothing else",
        "ru": "тонкое кольцо вокруг обложки, ничего лишнего",
    },
    "preset.retro": {
        "en": "VHS: scanlines, neon dots, heavy grain",
        "ru": "VHS: полосы, неоновые точки, высокая зернистость",
    },
    "preset.shorts": {
        "en": "vertical 1080x1920 for Shorts/Reels/TikTok",
        "ru": "вертикальный формат 1080x1920 для Shorts/Reels/TikTok",
    },
}


# --------------------------------------------------------------------------- #
#  Выбор языка
# --------------------------------------------------------------------------- #
def normalize(value: str | None) -> str | None:
    """Приводит 'ru_RU.UTF-8', 'Russian_Russia' и т.п. к коду языка."""
    if not value:
        return None
    tag = value.strip().lower().replace("-", "_")
    for lang in LANGUAGES:
        if tag.startswith(lang):
            return lang
    # Windows отдаёт локаль словом: 'Russian_Russia', 'English_United States'
    for lang, word in (("ru", "russian"), ("en", "english")):
        if tag.startswith(word):
            return lang
    return None


def detect_language() -> str:
    """Язык из окружения или локали системы; иначе — язык по умолчанию."""
    from_env = normalize(os.environ.get(ENV_VAR))
    if from_env:
        return from_env

    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        found = normalize(os.environ.get(var))
        if found:
            return found

    try:
        found = normalize(locale.getlocale()[0])
    except (ValueError, TypeError):
        found = None
    return found or DEFAULT_LANGUAGE


def set_language(lang: str | None) -> str:
    """Задаёт язык интерфейса и возвращает его.

    Значение кладётся в переменную окружения: процессы-воркеры поднимаются
    через spawn и наследуют окружение, но не состояние модуля.
    """
    global _current
    _current = normalize(lang) or detect_language()
    os.environ[ENV_VAR] = _current
    return _current


def get_language() -> str:
    """Текущий язык; при первом обращении определяется автоматически."""
    global _current
    if _current is None:
        _current = detect_language()
    return _current


def tr(key: str, **kwargs: object) -> str:
    """Сообщение по ключу на текущем языке, с подстановкой параметров."""
    variants = MESSAGES.get(key)
    if variants is None:                       # пропущенный ключ виден сразу,
        return key                             # но не роняет рендер
    text = variants.get(get_language()) or variants[DEFAULT_LANGUAGE]
    return text.format(**kwargs) if kwargs else text
