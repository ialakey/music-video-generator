# Command-line reference

**English** · [Русский](cli.ru.md)

[← back to README](../README.md) · [configuration](configuration.md) · [Python API](api.md)

```bash
python -m musicvideo [SUBCOMMAND] AUDIO [OPTIONS]
```

`AUDIO` is any file ffmpeg can read: mp3, wav, flac, m4a, ogg, opus, and so on.
The subcommand may be omitted — anything that is not a known subcommand is
treated as arguments to `render`, so these two lines are the same:

```bash
python -m musicvideo render track.mp3 -i art.jpg
python -m musicvideo track.mp3 -i art.jpg
```

## Subcommands

| Subcommand | What it does |
|------------|--------------|
| `render` | Renders the full video. The default. |
| `still` | Renders one frame to a PNG — a fast way to check settings. |
| `presets` | Prints the preset names with their descriptions. |
| `dump-config` | Prints (or writes) the final config with every default resolved. |

### `render`

```bash
python -m musicvideo track.mp3 -i art.jpg -p aesthetic -o output/video.mp4
```

Runs the whole pipeline: audio effects → spectrum analysis → frame rendering →
encoding with ffmpeg. Progress is shown on stderr with an ETA (suppressed with
`--quiet` and when stderr is not a terminal).

### `still`

```bash
python -m musicvideo still track.mp3 -i art.jpg --at 45 -o output/test.png
```

Takes every `render` flag plus `--at SECONDS` — where in the track to grab the
frame. Without `--at` the frame is taken at 25 % of the track's length. The
output extension is forced to `.png` unless it is already `.png`/`.jpg`/`.jpeg`.

The audio is still processed and analyzed (the visualizer has to show the real
spectrum at that moment), so a `still` is not instant — but it skips the
rendering and encoding of thousands of frames.

### `presets`

```bash
python -m musicvideo presets
```

Takes no arguments. Prints the six preset names and what each looks like.

### `dump-config`

```bash
python -m musicvideo dump-config track.mp3 -p aesthetic --dump-to my.json
```

Takes every `render` flag plus `--dump-to PATH` (`-`, the default, means
stdout). Writes the fully resolved config — defaults, preset, config file and
CLI flags already merged — so you can edit it and feed it back with `-c`.
Title and artist are filled in from the file's tags at this point too.

## Options

All of these work with `render`, `still` and `dump-config`.

### Input and output

| Flag | Meaning |
|------|---------|
| `AUDIO` | Positional. The audio file. Can also come from `audio_file` in a config. |
| `-i`, `--image PATH` | Background: an image, a folder of images, or the flag repeated several times. |
| `-o`, `--output PATH` | Where to write the result. Default: `output/video.mp4`. |
| `-c`, `--config PATH` | A JSON settings file. See [configuration](configuration.md). |
| `-p`, `--preset NAME` | One of `aesthetic`, `lofi`, `phonk`, `minimal`, `retro`, `shorts`. |
| `--lang {en,ru}` | Interface language. See [Language](#language). |

A folder passed to `-i` is expanded into every `.jpg`, `.jpeg`, `.png`,
`.webp`, `.bmp`, `.jfif` and `.avif` inside it, sorted by name, and the images
are crossfaded across the length of the clip. A path that does not exist is an
error, raised before the long work starts.

### Text

| Flag | Meaning |
|------|---------|
| `--title TEXT` | Track title. Falls back to the file's tag, then to the file name. |
| `--artist TEXT` | Artist. Falls back to the `artist` or `album_artist` tag. |

### Cover art

| Flag | Meaning |
|------|---------|
| `--cover PATH` | The cover image. |
| `--no-cover` | Draw no cover at all. |

Without `--cover` the cover is resolved in this order: the artwork embedded in
the audio file's tags → the first background image. `--no-cover` skips this
entirely.

### Visualizer

| Flag | Meaning |
|------|---------|
| `--style NAME` | `circle`, `bars`, `mirror`, `wave`, `ring` or `dots`. |
| `--color HEX` | Main color. `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` or a PIL color name. |
| `--color2 HEX` | Second color; the bands are graded from `color` to `color2`. |
| `--no-visualizer` | Draw no visualizer. |
| `--no-progress` | Draw no progress bar. |
| `--grain 0..1` | Film grain. `0` turns it off and shrinks the file a lot. |

### Audio

| Flag | Meaning |
|------|---------|
| `--speed X` | `0.85` = slowed, `1.2` = sped up. Pitch moves with the tempo. |
| `--reverb 0..1` | Reverb amount. `0` is off. |
| `--bass dB` | Low-frequency boost, in decibels. |
| `--start SEC` | Skip this many seconds of the source. |
| `--length SEC` | Use only this many seconds of the source (measured before `--speed`). |

`--start` and `--length` cut the *source*, so with `--speed 0.85` a
`--length 40` excerpt turns into roughly 47 seconds of video.

### Video

| Flag | Meaning |
|------|---------|
| `--size WxH` | Resolution, e.g. `1920x1080` or `1080x1920`. Both sides must be even. |
| `--fps N` | Frames per second. |
| `--crf N` | x264 quality; lower is better and bigger. Default `21`. |
| `--preview SEC` | Render only the first SEC seconds; the audio is trimmed to match. |
| `--workers N` | Render processes. `1` disables parallelism. |
| `--quiet` | No progress bar and no messages. |

With `--workers 0` (the default) the worker count is one less than the number
of CPU cores, capped so that each worker gets at least ~40 frames — short
previews therefore run in fewer processes than a full track.

## Language

The interface speaks English and Russian. The language is chosen once at
startup, in this order:

1. `--lang en` / `--lang ru` on the command line;
2. the `MUSICVIDEO_LANG` environment variable;
3. the system locale (`LC_ALL`, `LC_MESSAGES`, `LANGUAGE`, `LANG`, then
   Python's own locale — `ru_RU.UTF-8` and Windows' `Russian_Russia` are both
   recognized);
4. English, as the fallback.

```bash
python -m musicvideo track.mp3 -i art.jpg --lang en    # this run only
export MUSICVIDEO_LANG=en                              # this shell
```

`--lang` covers help text, progress, log lines and error messages. It is read
before the parser is built, so `--lang ru --help` already prints Russian help.
The chosen language is passed to the render worker processes through the
environment, so their messages match.

A handful of strings still come from Python's own `argparse` and stay English
whatever the setting — the words `error:` and messages like `invalid int
value: 'abc'` or `invalid choice`. Python ships no Russian translation for
them.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | Render error: ffmpeg failed, a file is missing, a value is out of range. |
| `2` | Bad configuration: unknown field, malformed JSON, unknown preset. |
| `130` | Interrupted with Ctrl+C. |

## Examples

```bash
# the reference look, straight from a preset
python -m musicvideo track.mp3 -i art.jpg -p aesthetic

# check the settings on one frame before committing to a render
python -m musicvideo still track.mp3 -i art.jpg -p lofi --at 30

# a 720p draft: small, fast, grainless
python -m musicvideo track.mp3 -i art.jpg --size 1280x720 --fps 24 --grain 0

# 40 seconds from the chorus, red mirrored bars
python -m musicvideo track.mp3 -i art.jpg --start 62 --length 40 \
    --style mirror --color "#ff2d4a" --color2 "#ffffff"

# a slideshow at half speed, vertical, for Shorts
python -m musicvideo track.mp3 -i pics/ -p shorts --speed 0.85 --reverb 0.5

# start from a preset, then hand-edit the rest
python -m musicvideo dump-config track.mp3 -p retro --dump-to retro.json
python -m musicvideo track.mp3 -c retro.json
```
