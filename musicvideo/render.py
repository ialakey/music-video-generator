"""Сборка кадра из слоёв и полный конвейер рендера."""
from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
from PIL import Image

from . import ffmpeg
from .audio import Analysis, analyze
from .config import Config, TextItemCfg
from .i18n import tr
from .layers import Background, Cover, Overlay, ProgressBar, TextLayer, Visualizer
from .layers.background import collect_images

#: Частота дискретизации для анализа и итогового звука.
SAMPLE_RATE = 44100


class FrameRenderer:
    """Держит подготовленные слои и собирает кадр по его номеру."""

    def __init__(self, cfg: Config, analysis: Analysis, duration: float,
                 cover_image: Path | None = None) -> None:
        self.cfg = cfg
        self.analysis = analysis
        self.duration = duration
        self.size = (cfg.video.width, cfg.video.height)
        self.fps = cfg.video.fps

        bg_images = collect_images(cfg.background.image)
        self.background = Background(cfg.background, self.size, duration)
        self.cover = Cover(
            cfg.cover, self.size,
            cover_image or (bg_images[0] if bg_images else None),
        )
        self.visualizer = Visualizer(cfg.visualizer, self.size, analysis)
        self.text = TextLayer(self._text_items(), self.size)
        self.progress = ProgressBar(cfg.progress, self.size, duration)
        self.overlay = Overlay(
            cfg.overlay, self.size, duration,
            grain=cfg.background.grain, grain_size=cfg.background.grain_size,
        )

    def _text_items(self) -> list[TextItemCfg]:
        t = self.cfg.text
        return [t.title, t.artist, *t.extra]

    # ------------------------------------------------------------------ #
    def frame(self, index: int) -> np.ndarray:
        """Готовый кадр (H, W, 3) uint8."""
        a = self.analysis
        i = a.clamp(index)
        t = index / self.fps
        bass = float(a.bass[i])
        beat = float(a.beat[i])
        rng = np.random.default_rng(1000 + index)

        canvas = self.background.frame(t, bass, beat, rng).convert("RGBA")
        self.cover.paste(canvas, t, bass)

        viz = self.visualizer.render(a, i)
        if viz is not None:
            image, pos = viz
            canvas.alpha_composite(image, pos)

        self.text.paste(canvas, t)
        self.progress.paste(canvas, t, self.text_alpha(t))

        arr = np.asarray(canvas.convert("RGB"), dtype=np.float32)
        arr = self.overlay.apply(arr, t, index, beat)
        return np.clip(arr, 0.0, 255.0).astype(np.uint8)

    def text_alpha(self, t: float) -> float:
        """Общая прозрачность UI — совпадает с появлением заголовка."""
        item = self.cfg.text.title
        if item.fade_in <= 0:
            return 1.0 if t >= item.delay else 0.0
        return float(np.clip((t - item.delay) / item.fade_in, 0.0, 1.0))


# --------------------------------------------------------------------------- #
#  Параллельный рендер
# --------------------------------------------------------------------------- #
_WORKER: FrameRenderer | None = None


def _init_worker(cfg: Config, analysis: Analysis, duration: float,
                 cover: Path | None) -> None:
    global _WORKER
    _WORKER = FrameRenderer(cfg, analysis, duration, cover)


def _render_one(index: int) -> bytes:
    assert _WORKER is not None
    return _WORKER.frame(index).tobytes()


def iter_frames(
    cfg: Config, analysis: Analysis, duration: float, n_frames: int,
    cover: Path | None, workers: int,
) -> Iterator[bytes]:
    """Выдаёт кадры по порядку — в одном процессе или пулом воркеров."""
    if workers <= 1:
        renderer = FrameRenderer(cfg, analysis, duration, cover)
        for i in range(n_frames):
            yield renderer.frame(i).tobytes()
        return

    ctx = mp.get_context("spawn")
    pool = ctx.Pool(
        processes=workers, initializer=_init_worker,
        initargs=(cfg, analysis, duration, cover),
    )
    try:
        chunk = max(1, min(16, n_frames // (workers * 8) or 1))
        yield from pool.imap(_render_one, range(n_frames), chunksize=chunk)
    finally:
        pool.terminate()
        pool.join()


# --------------------------------------------------------------------------- #
#  Конвейер целиком
# --------------------------------------------------------------------------- #
ProgressFn = Callable[[int, int, float], None]


def render_video(cfg: Config, on_progress: ProgressFn | None = None,
                 log: Callable[[str], None] = print) -> Path:
    """Готовит звук, анализирует его и кодирует итоговый ролик."""
    ffmpeg.check_tools()
    _validate(cfg)

    src = Path(cfg.audio_file).expanduser()
    info = ffmpeg.probe(src)
    workdir = Path(tempfile.mkdtemp(prefix="musicvideo-"))

    try:
        wav = workdir / "audio.wav"
        log(tr("log.audio"))
        duration = ffmpeg.render_audio(src, wav, cfg.audio, info, SAMPLE_RATE)

        full_frames = max(1, int(round(duration * cfg.video.fps)))
        n_frames = full_frames
        if cfg.preview:
            n_frames = max(1, min(full_frames, int(round(cfg.preview * cfg.video.fps))))

        log(tr("log.analysis"))
        samples = ffmpeg.decode_mono(wav, SAMPLE_RATE)
        analysis = analyze(samples, SAMPLE_RATE, cfg.video.fps, cfg.analysis, full_frames)
        del samples

        cover = _resolve_cover(cfg, src, workdir)
        workers = _worker_count(cfg.workers, n_frames)
        log(tr("log.render", frames=n_frames, width=cfg.video.width,
              height=cfg.video.height, fps=cfg.video.fps, workers=workers))

        started = time.monotonic()
        encoder = ffmpeg.VideoEncoder(cfg.output, wav, cfg.video)
        try:
            frames = iter_frames(cfg, analysis, duration, n_frames, cover, workers)
            for i, payload in enumerate(frames, start=1):
                encoder.write(payload)
                if on_progress is not None:
                    on_progress(i, n_frames, time.monotonic() - started)
            encoder.close()
        except BaseException:
            encoder.abort()
            raise

        return Path(cfg.output)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _validate(cfg: Config) -> None:
    """Быстрые проверки до долгой работы: пути, размеры, имена стилей."""
    from .layers.visualizer import STYLES

    collect_images(cfg.background.image)          # бросит, если пути нет
    if cfg.cover.enabled and cfg.cover.image:
        if not Path(cfg.cover.image).expanduser().exists():
            raise FileNotFoundError(tr("err.cover_missing", path=cfg.cover.image))

    if cfg.visualizer.style not in STYLES:
        raise ValueError(
            tr("err.unknown_style", name=cfg.visualizer.style,
              available=", ".join(STYLES))
        )
    if cfg.video.width < 16 or cfg.video.height < 16:
        raise ValueError(
            tr("err.frame_too_small", width=cfg.video.width, height=cfg.video.height)
        )
    if cfg.video.width % 2 or cfg.video.height % 2:
        raise ValueError(
            tr("err.odd_size", pixel_format=cfg.video.pixel_format,
              width=cfg.video.width, height=cfg.video.height)
        )
    if cfg.video.fps < 1:
        raise ValueError(tr("err.bad_fps", value=cfg.video.fps))
    if cfg.audio.speed <= 0:
        raise ValueError(tr("err.bad_speed", value=cfg.audio.speed))


def _worker_count(requested: int, n_frames: int) -> int:
    if requested > 0:
        return max(1, requested)
    cpus = os.cpu_count() or 2
    return max(1, min(cpus - 1 if cpus > 2 else 1, max(1, n_frames // 40)))


def _resolve_cover(cfg: Config, audio: Path, workdir: Path) -> Path | None:
    """Обложка: из конфига, из тегов файла или первая картинка фона."""
    if not cfg.cover.enabled:
        return None
    if cfg.cover.image:
        path = Path(cfg.cover.image).expanduser()
        if not path.exists():
            raise FileNotFoundError(tr("err.cover_missing", path=path))
        return path

    embedded = ffmpeg.extract_cover(audio, workdir / "cover.jpg")
    if embedded is not None:
        return embedded

    images = collect_images(cfg.background.image)
    return images[0] if images else None


def render_still(cfg: Config, at: float = 0.0) -> Image.Image:
    """Один кадр без кодирования — для быстрой проверки настроек."""
    ffmpeg.check_tools()
    _validate(cfg)
    src = Path(cfg.audio_file).expanduser()
    info = ffmpeg.probe(src)
    workdir = Path(tempfile.mkdtemp(prefix="musicvideo-still-"))
    try:
        wav = workdir / "audio.wav"
        duration = ffmpeg.render_audio(src, wav, cfg.audio, info, SAMPLE_RATE)
        samples = ffmpeg.decode_mono(wav, SAMPLE_RATE)
        n_frames = max(1, int(round(duration * cfg.video.fps)))
        analysis = analyze(samples, SAMPLE_RATE, cfg.video.fps, cfg.analysis, n_frames)
        cover = _resolve_cover(cfg, src, workdir)
        renderer = FrameRenderer(cfg, analysis, duration, cover)
        index = int(round(float(np.clip(at, 0.0, duration)) * cfg.video.fps))
        return Image.fromarray(renderer.frame(min(index, n_frames - 1)), "RGB")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
