# Python API

[English](api.md) · **Русский**

[← к README](../README.ru.md) · [CLI](cli.ru.md) · [конфигурация](configuration.ru.md)

Пакет написан так, чтобы им можно было управлять из Python, а не только из
командной строки. Установщика пока нет — импортируйте его из каталога проекта
или добавьте корень проекта в `sys.path`.

## Самая короткая полезная программа

```python
from musicvideo.config import load_config
from musicvideo.render import render_video

def main():
    cfg = load_config(None, {
        "audio_file": "track.mp3",
        "background": {"image": "art.jpg"},
        "text": {"title": {"text": "Way Down We Go"},
                 "artist": {"text": "Kaleo"}},
    }, preset="aesthetic")
    print(render_video(cfg))

if __name__ == "__main__":
    main()
```

> **Блок `if __name__ == "__main__":` обязателен.** Рендер использует пул
> процессов в режиме `spawn`, и каждый воркер заново импортирует модуль,
> из которого был запущен. Без этого блока каждый воркер выполнит ваш скрипт
> сверху донизу и запустит собственный рендер — рекурсивно. Альтернатива —
> `"workers": 1` в конфиге, что отключает пул.

## `musicvideo.config`

### `load_config(path=None, overrides=None, preset=None) -> Config`

Собирает итоговый конфиг из четырёх слоёв, по порядку: умолчания → пресет →
JSON-файл по пути `path` → словарь `overrides`.

```python
cfg = load_config("my.json", {"video": {"fps": 24}}, preset="lofi")
```

`overrides` — обычный вложенный словарь той же формы, что и JSON-файл.
Частичные секции сливаются по полям, поэтому пример выше меняет только `fps`
и не трогает остальную секцию `video`.

Бросает `ConfigError` при отсутствующем файле, битом JSON, неизвестном пресете
или неизвестном поле.

### `Config` и dataclass'ы секций

`Config` — обычный вложенный dataclass, поэтому всё читается и пишется
напрямую:

```python
cfg.video.fps = 24
cfg.visualizer.color = "#ff2d4a"
cfg.text.title.text = "Way Down We Go"
cfg.background.image = ["a.jpg", "b.jpg", "c.jpg"]
```

Секции: `VideoCfg`, `AudioCfg`, `AnalysisCfg`, `BackgroundCfg`, `CoverCfg`,
`VisualizerCfg`, `TextCfg` (содержит элементы `TextItemCfg`), `ProgressCfg`
и `OverlayCfg`. Все поля перечислены в
[справочнике по конфигурации](configuration.ru.md).

Два вспомогательных метода:

| Метод | Что делает |
|-------|------------|
| `cfg.to_dict()` | Весь конфиг вложенными словарями. |
| `cfg.save(path)` | Записывает его как JSON с отступами в UTF-8. |

### `deep_merge(base, override) -> dict`

Рекурсивное слияние словарей, не меняющее аргументы. Удобно, когда
переопределения собираются из нескольких частей:

```python
from musicvideo.config import deep_merge

look = deep_merge(BRAND_STYLE, {"text": {"title": {"text": title}}})
cfg = load_config(None, look, preset="shorts")
```

### `ConfigError`

Бросается на любую проблему с самими настройками. CLI превращает её в код
возврата 2.

## `musicvideo.render`

### `render_video(cfg, on_progress=None, log=print) -> Path`

Весь конвейер: аудиоэффекты → анализ → кадры → кодирование. Возвращает путь
к готовому файлу.

- `on_progress(done, total, elapsed)` вызывается после каждого закодированного
  кадра. `elapsed` — секунды с начала рендера.
- `log(message)` получает сообщения об этапах. Передайте `lambda _: None`,
  чтобы их заглушить.

```python
def on_progress(done, total, elapsed):
    if done % 100 == 0 or done == total:
        print(f"{done}/{total} кадров, {elapsed:.0f} с")

render_video(cfg, on_progress, log=lambda _: None)
```

Бросает `FFmpegError`, `ConfigError`, `FileNotFoundError` или `ValueError` —
и делает это до того, как получится испорченный файл, либо вместо него.
Недописанный файл не остаётся: при любом исключении кодировщик аварийно
завершается.

### `render_still(cfg, at=0.0) -> PIL.Image.Image`

Один кадр на секунде `at` *обработанного* звука, возвращаемый как изображение
PIL, а не записываемый куда-либо. Звук при этом всё равно обрабатывается
и анализируется, поэтому вызов быстрый по сравнению с полным рендером,
но не мгновенный.

```python
from musicvideo.render import render_still

render_still(cfg, at=45.0).save("proba.png")
```

Это правильный инструмент для перебора настроек:

```python
for radius in (240, 280, 320):
    cfg.visualizer.radius = radius
    render_still(cfg, at=30.0).save(f"radius-{radius}.png")
```

### `FrameRenderer`

Держит подготовленные слои и рисует кадр по его номеру. Именно им пользуются
процессы-воркеры; берите его, когда нужны кадры без ffmpeg.

```python
from musicvideo.render import FrameRenderer

renderer = FrameRenderer(cfg, analysis, duration, cover_path)
frame = renderer.frame(120)     # массив numpy uint8, форма (H, W, 3)
```

### `iter_frames(cfg, analysis, duration, n_frames, cover, workers)`

Выдаёт сырые байты кадров по порядку — из одного процесса или из пула.
Пригодится, если кадры нужно отправить не во встроенный кодировщик.

## `musicvideo.ffmpeg`

| Функция | Что делает |
|---------|------------|
| `check_tools()` | Бросает `FFmpegError`, если нет `ffmpeg` или `ffprobe`. |
| `probe(path) -> MediaInfo` | Длительность, частота дискретизации, каналы, теги названия и исполнителя. |
| `render_audio(src, dst, cfg, info, sample_rate) -> float` | Применяет цепочку эффектов, пишет WAV, возвращает его длительность. |
| `decode_mono(path, sample_rate) -> np.ndarray` | Декодирует в моно float32 в [−1, 1]. |
| `build_audio_filters(cfg, sample_rate, out_duration) -> list[str]` | Цепочка `-af` списком строк-фильтров. |
| `extract_cover(audio_path, dst) -> Path \| None` | Вытаскивает картинку из тегов или возвращает `None`. |

### `VideoEncoder`

Тонкая обёртка над процессом ffmpeg, который читает сырые RGB-кадры из stdin
и склеивает их с готовым аудиофайлом. Работает как контекстный менеджер:
корректно закрывает кодировщик при успехе и прерывает при исключении.

```python
from musicvideo.ffmpeg import VideoEncoder

with VideoEncoder("out.mp4", "audio.wav", cfg.video) as enc:
    for i in range(n_frames):
        enc.write(renderer.frame(i))
```

## `musicvideo.audio`

### `analyze(samples, sample_rate, fps, cfg, n_frames=None) -> Analysis`

Превращает моносигнал в покадровые данные для визуализации.

```python
from musicvideo.audio import analyze
from musicvideo.ffmpeg import decode_mono

samples = decode_mono("track.mp3", 44100)
a = analyze(samples, 44100, 30, cfg.analysis)
```

`Analysis` хранит для `n_frames` кадров всё, нормированное в 0–1:

| Поле | Форма | Что это |
|------|-------|---------|
| `bands` | `(n_frames, n_bands)` | Уровни частотных полос. |
| `freqs` | `(n_bands,)` | Центральные частоты полос, Гц. |
| `bass`, `mid`, `high` | `(n_frames,)` | Огибающие по частотным диапазонам. |
| `level` | `(n_frames,)` | Общая громкость. |
| `beat` | `(n_frames,)` | Импульс удара: быстрая атака, плавный спад. |

Это та часть, которую стоит взять, если музыкой нужно управлять чем-то
ещё — светом, игрой, другим рендерером.

### `slice_bands(analysis, spec_range) -> tuple[int, int]`

Диапазон индексов полос для `"full"`, `"bass"`, `"mid"` или `"high"`.

## `musicvideo.presets`

```python
from musicvideo.presets import PRESETS, describe, descriptions

PRESETS["lofi"]           # пресет как частичный словарь конфига
describe("lofi")          # его однострочное описание на текущем языке
descriptions()            # {имя: описание} для всех пресетов
```

Пресеты — обычные словари, поэтому свой пресет это просто словарь: его можно
зарегистрировать в `PRESETS` или передать прямо как `overrides`:

```python
MY_LOOK = {
    "visualizer": {"style": "ring", "color": "#7dd3fc", "radius": 300.0},
    "overlay": {"vignette": 0.5, "scanlines": 0.08},
}
cfg = load_config(None, deep_merge(MY_LOOK, {"audio_file": "track.mp3"}))
```

## `musicvideo.layers`

Пять классов-слоёв — `Background`, `Cover`, `Visualizer`, `TextLayer`,
`ProgressBar` и `Overlay` — каждый принимает свою секцию конфига и размер
кадра и рисует в холст PIL. `FrameRenderer` показывает, как они складываются
вместе; в своём конвейере их можно использовать поодиночке.

`collect_images(spec)` из `musicvideo.layers.background` разворачивает путь,
папку или список в отсортированный список файлов изображений и бросает
`FileNotFoundError` на всё отсутствующее.

## `musicvideo.i18n`

Все сообщения пакета — строки журнала, тексты исключений, справка CLI — берутся
из одного каталога и существуют на английском и русском.

| Имя | Что это |
|-----|---------|
| `tr(key, **kwargs)` | Сообщение по ключу на текущем языке, с подстановкой. |
| `set_language(lang)` | Задаёт язык и возвращает его. `None` — определить заново. |
| `get_language()` | Текущий язык; при первом обращении определяется сам. |
| `detect_language()` | `MUSICVIDEO_LANG`, затем локаль, затем английский. |
| `MESSAGES` | Каталог: `{ключ: {"en": ..., "ru": ...}}`. |
| `LANGUAGES` | `("en", "ru")`. |

CLI вызывает `set_language()` при старте; библиотечному коду это не обязательно —
язык определяется при первом обращении. Задать его явно стоит тогда, когда нужно
закрепить язык исключений, которые ваша программа ловит и печатает сама:

```python
from musicvideo.i18n import set_language
from musicvideo.render import render_video

set_language("ru")
try:
    render_video(cfg)
except Exception as e:
    print(e)          # по-русски независимо от локали машины
```

`set_language` заодно записывает `MUSICVIDEO_LANG` в окружение — так настройка
доходит до процессов-воркеров: они поднимаются через `spawn` и наследуют
окружение, но не состояние модуля.

Неизвестный ключ возвращает сам себя, а не бросает исключение, поэтому
пропущенный перевод не уронит рендер на середине.

## `musicvideo.draw`

Общие утилиты рисования — пригодятся, если пишете свой слой:

| Функция | Что делает |
|---------|------------|
| `parse_color(value, default)` | `#rgb` / `#rgba` / `#rrggbb` / `#rrggbbaa` / имя PIL → кортеж RGBA. |
| `mix(a, b, t)` | Линейное смешение цветов. |
| `gradient_colors(a, b, n)` | `n` цветов от `a` к `b`. |
| `with_alpha(color, factor)` | Тот же цвет с умноженной альфой. |
| `load_font(name, size)` | Шрифт из `assets/fonts` или системный, с запасными вариантами. |
| `ui_scale(size)` | Множитель из «пикселей при короткой стороне 1080» в реальный кадр. |

## Пакетный рендер

Проще всего запускать по треку на процесс, но и цикл внутри одного процесса
работает — главное, не терять защитный блок:

```python
from pathlib import Path
from musicvideo.config import load_config
from musicvideo.render import render_video

def main():
    for track in Path("tracks").glob("*.mp3"):
        cfg = load_config(None, {
            "audio_file": str(track),
            "output": f"output/{track.stem}.mp4",
            "background": {"image": "art.jpg"},
        }, preset="aesthetic")
        render_video(cfg, log=lambda _: None)
        print("готово:", track.name)

if __name__ == "__main__":
    main()
```

Название и исполнитель здесь *не* подставляются из тегов файла — это делает
CLI. Чтобы получить то же поведение, прочитайте их сами:

```python
from musicvideo.ffmpeg import probe

info = probe(track)
cfg.text.title.text = info.title or track.stem
cfg.text.artist.text = info.artist or ""
```
