# Python API

**English** · [Русский](api.ru.md)

[← back to README](../README.md) · [CLI](cli.md) · [configuration](configuration.md)

The package is written to be driven from Python, not only from the command
line. There is no installer yet — import it from the project directory, or add
the project root to `sys.path`.

## The shortest useful program

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

> **The `if __name__ == "__main__":` guard is required.** Rendering uses a
> `spawn` process pool, and every worker re-imports the module it was started
> from. Without the guard, each worker runs your script top to bottom and
> starts its own render — recursively. The alternative is `"workers": 1` in the
> config, which disables the pool.

## `musicvideo.config`

### `load_config(path=None, overrides=None, preset=None) -> Config`

Builds the final config from four layers, in order: defaults → preset →
the JSON file at `path` → the `overrides` dictionary.

```python
cfg = load_config("my.json", {"video": {"fps": 24}}, preset="lofi")
```

`overrides` is an ordinary nested dict with the same shape as the JSON file.
Partial sections merge field by field, so the snippet above changes only `fps`
and leaves the rest of `video` alone.

Raises `ConfigError` for a missing file, malformed JSON, an unknown preset or
an unknown field.

### `Config` and the section dataclasses

`Config` is a plain nested dataclass, so everything is readable and writable:

```python
cfg.video.fps = 24
cfg.visualizer.color = "#ff2d4a"
cfg.text.title.text = "Way Down We Go"
cfg.background.image = ["a.jpg", "b.jpg", "c.jpg"]
```

The sections are `VideoCfg`, `AudioCfg`, `AnalysisCfg`, `BackgroundCfg`,
`CoverCfg`, `VisualizerCfg`, `TextCfg` (holding `TextItemCfg` items),
`ProgressCfg` and `OverlayCfg`. Every field is listed in
[the configuration reference](configuration.md).

Two helpers:

| Method | What it does |
|--------|--------------|
| `cfg.to_dict()` | The whole config as nested dicts. |
| `cfg.save(path)` | Writes it as indented UTF-8 JSON. |

### `deep_merge(base, override) -> dict`

Recursive dict merge that does not mutate its arguments. Useful for building
overrides out of several pieces:

```python
from musicvideo.config import deep_merge

look = deep_merge(BRAND_STYLE, {"text": {"title": {"text": title}}})
cfg = load_config(None, look, preset="shorts")
```

### `ConfigError`

Raised for anything wrong with the settings themselves. The CLI turns it into
exit code 2.

## `musicvideo.render`

### `render_video(cfg, on_progress=None, log=print) -> Path`

The whole pipeline: audio effects → analysis → frames → encoding. Returns the
path to the finished file.

- `on_progress(done, total, elapsed)` is called after each encoded frame.
  `elapsed` is seconds since the render started.
- `log(message)` receives the stage messages. Pass `lambda _: None` to silence
  them.

```python
def on_progress(done, total, elapsed):
    if done % 100 == 0 or done == total:
        print(f"{done}/{total} frames, {elapsed:.0f}s")

render_video(cfg, on_progress, log=lambda _: None)
```

Raises `FFmpegError`, `ConfigError`, `FileNotFoundError` or `ValueError` — all
of them before or instead of producing a broken file. A partially written file
is not left behind: the encoder is aborted on any exception.

### `render_still(cfg, at=0.0) -> PIL.Image.Image`

One frame at second `at` of the *processed* audio, returned as a PIL image
rather than written anywhere. The audio is still processed and analyzed, so
this is fast relative to a full render but not instant.

```python
from musicvideo.render import render_still

render_still(cfg, at=45.0).save("test.png")
```

This is the right tool for a settings sweep:

```python
for radius in (240, 280, 320):
    cfg.visualizer.radius = radius
    render_still(cfg, at=30.0).save(f"radius-{radius}.png")
```

### `FrameRenderer`

Holds the prepared layers and renders a frame by its index. This is what the
worker processes use; reach for it when you want frames without ffmpeg.

```python
from musicvideo.render import FrameRenderer

renderer = FrameRenderer(cfg, analysis, duration, cover_path)
frame = renderer.frame(120)     # numpy uint8 array, shape (H, W, 3)
```

### `iter_frames(cfg, analysis, duration, n_frames, cover, workers)`

Yields raw frame bytes in order, from one process or from a pool. Useful for
feeding frames somewhere other than the built-in encoder.

## `musicvideo.ffmpeg`

| Function | What it does |
|----------|--------------|
| `check_tools()` | Raises `FFmpegError` if `ffmpeg` or `ffprobe` is missing. |
| `probe(path) -> MediaInfo` | Duration, sample rate, channels, title and artist tags. |
| `render_audio(src, dst, cfg, info, sample_rate) -> float` | Applies the effect chain, writes a WAV, returns its duration. |
| `decode_mono(path, sample_rate) -> np.ndarray` | Decodes to mono float32 in [−1, 1]. |
| `build_audio_filters(cfg, sample_rate, out_duration) -> list[str]` | The `-af` chain as a list of filter strings. |
| `extract_cover(audio_path, dst) -> Path \| None` | Pulls artwork out of the tags, or `None`. |

### `VideoEncoder`

A thin wrapper over an ffmpeg process reading raw RGB frames on stdin and
muxing them with a prepared audio file. Usable as a context manager, which
closes the encoder cleanly on success and aborts it on an exception:

```python
from musicvideo.ffmpeg import VideoEncoder

with VideoEncoder("out.mp4", "audio.wav", cfg.video) as enc:
    for i in range(n_frames):
        enc.write(renderer.frame(i))
```

## `musicvideo.audio`

### `analyze(samples, sample_rate, fps, cfg, n_frames=None) -> Analysis`

Turns a mono signal into per-frame visualization data.

```python
from musicvideo.audio import analyze
from musicvideo.ffmpeg import decode_mono

samples = decode_mono("track.mp3", 44100)
a = analyze(samples, 44100, 30, cfg.analysis)
```

`Analysis` holds, for `n_frames` frames, everything normalized to 0–1:

| Field | Shape | What it is |
|-------|-------|------------|
| `bands` | `(n_frames, n_bands)` | Frequency band levels. |
| `freqs` | `(n_bands,)` | Band center frequencies, Hz. |
| `bass`, `mid`, `high` | `(n_frames,)` | Envelopes per frequency range. |
| `level` | `(n_frames,)` | Overall loudness. |
| `beat` | `(n_frames,)` | Beat impulse: fast attack, smooth decay. |

This is the part to use if you want to drive something else — lights, a game,
another renderer — from the music.

### `slice_bands(analysis, spec_range) -> tuple[int, int]`

The band index range for `"full"`, `"bass"`, `"mid"` or `"high"`.

## `musicvideo.presets`

```python
from musicvideo.presets import PRESETS, describe, descriptions

PRESETS["lofi"]           # the preset as a partial config dict
describe("lofi")          # its one-line description, in the current language
descriptions()            # {name: description} for all of them
```

Presets are plain dicts, so a custom one is just a dict — either registered
into `PRESETS` or passed straight as `overrides`:

```python
MY_LOOK = {
    "visualizer": {"style": "ring", "color": "#7dd3fc", "radius": 300.0},
    "overlay": {"vignette": 0.5, "scanlines": 0.08},
}
cfg = load_config(None, deep_merge(MY_LOOK, {"audio_file": "track.mp3"}))
```

## `musicvideo.layers`

The five layer classes — `Background`, `Cover`, `Visualizer`, `TextLayer`,
`ProgressBar` and `Overlay` — each take their config section, the frame size,
and render into a PIL canvas. `FrameRenderer` is the example of how they fit
together; a custom pipeline can use them individually.

`collect_images(spec)` from `musicvideo.layers.background` expands a path, a
folder or a list into a sorted list of image files, raising `FileNotFoundError`
for anything missing.

## `musicvideo.i18n`

Every message the package produces — log lines, exception text, CLI help — comes
from one catalog and exists in English and Russian.

| Name | What it is |
|------|------------|
| `tr(key, **kwargs)` | The message for `key` in the current language, formatted. |
| `set_language(lang)` | Sets the language and returns it. `None` re-detects. |
| `get_language()` | The current language, detecting it on first use. |
| `detect_language()` | `MUSICVIDEO_LANG`, then the locale, then English. |
| `MESSAGES` | The catalog: `{key: {"en": ..., "ru": ...}}`. |
| `LANGUAGES` | `("en", "ru")`. |

The CLI calls `set_language()` at startup; library code does not have to, since
the language is detected on first use. Setting it explicitly is the way to pin
the language of the exceptions your own program catches and prints:

```python
from musicvideo.i18n import set_language
from musicvideo.render import render_video

set_language("en")
try:
    render_video(cfg)
except Exception as e:
    print(e)          # English regardless of the machine's locale
```

`set_language` also writes `MUSICVIDEO_LANG` into the environment, which is how
the setting reaches the render workers — they are started with `spawn` and
inherit the environment, not the module state.

An unknown key returns the key itself rather than raising, so a missing
translation cannot take down a render mid-way.

## `musicvideo.draw`

Shared drawing helpers, useful when writing a layer of your own:

| Function | What it does |
|----------|--------------|
| `parse_color(value, default)` | `#rgb` / `#rgba` / `#rrggbb` / `#rrggbbaa` / PIL name → RGBA tuple. |
| `mix(a, b, t)` | Linear color blend. |
| `gradient_colors(a, b, n)` | `n` colors stepping from `a` to `b`. |
| `with_alpha(color, factor)` | The same color with its alpha scaled. |
| `load_font(name, size)` | Font from `assets/fonts` or the system, with fallbacks. |
| `ui_scale(size)` | The multiplier from 1080-reference pixels to the actual frame. |

## Batch rendering

One track per process invocation is the simplest approach, but a loop inside
one process works too — just keep the guard:

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
        print("done:", track.name)

if __name__ == "__main__":
    main()
```

Title and artist are *not* filled in from the file tags here — that happens in
the CLI. To get the same behaviour, read them yourself:

```python
from musicvideo.ffmpeg import probe

info = probe(track)
cfg.text.title.text = info.title or track.stem
cfg.text.artist.text = info.artist or ""
```
