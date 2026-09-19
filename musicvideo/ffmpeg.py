"""Мост к ffmpeg: декодирование звука, аудиоэффекты и кодирование видео."""
from __future__ import annotations

import json
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import AudioCfg, VideoCfg
from .i18n import tr


class FFmpegError(RuntimeError):
    """ffmpeg/ffprobe отсутствует или завершился с ошибкой."""


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegError(
            tr("err.tool_missing", name=name)
        )
    return path


def check_tools() -> None:
    """Проверяет наличие ffmpeg и ffprobe до начала долгой работы."""
    _tool("ffmpeg")
    _tool("ffprobe")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-12:]
        raise FFmpegError(
            tr("err.tool_failed", tool=Path(cmd[0]).stem,
               code=proc.returncode, details="\n  ".join(tail))
        )
    return proc


# --------------------------------------------------------------------------- #
#  Метаданные
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MediaInfo:
    duration: float
    sample_rate: int
    channels: int
    title: str | None = None
    artist: str | None = None


def probe(path: str | Path) -> MediaInfo:
    """Читает длительность, параметры аудиопотока и теги файла."""
    p = Path(path)
    if not p.exists():
        raise FFmpegError(tr("err.audio_missing", path=p))

    out = _run([
        _tool("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", "-select_streams", "a:0", str(p),
    ]).stdout
    data = json.loads(out or b"{}")

    streams = data.get("streams") or []
    if not streams:
        raise FFmpegError(tr("err.no_audio_stream", path=p))
    stream = streams[0]
    fmt = data.get("format") or {}

    duration = float(fmt.get("duration") or stream.get("duration") or 0.0)
    if duration <= 0:
        raise FFmpegError(tr("err.no_duration", path=p))

    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    tags.update({k.lower(): v for k, v in (stream.get("tags") or {}).items()})

    return MediaInfo(
        duration=duration,
        sample_rate=int(stream.get("sample_rate") or 44100),
        channels=int(stream.get("channels") or 2),
        title=tags.get("title"),
        artist=tags.get("artist") or tags.get("album_artist"),
    )


# --------------------------------------------------------------------------- #
#  Цепочка аудиоэффектов
# --------------------------------------------------------------------------- #
def build_audio_filters(cfg: AudioCfg, sample_rate: int, out_duration: float) -> list[str]:
    """Собирает -af цепочку: скорость -> бас -> реверб -> громкость -> фейды."""
    f: list[str] = []

    if abs(cfg.speed - 1.0) > 1e-3:
        # asetrate меняет и темп, и высоту — это и есть эффект "slowed"/"sped up"
        f.append(f"asetrate={int(round(sample_rate * cfg.speed))}")
        f.append(f"aresample={sample_rate}")

    if abs(cfg.bass_boost) > 1e-3:
        f.append(f"bass=g={cfg.bass_boost:.2f}:f=110:width_type=q:w=0.7")

    if cfg.reverb > 1e-3:
        f.extend(_reverb_filters(cfg.reverb, cfg.reverb_room))

    if cfg.normalize:
        f.append("loudnorm=I=-14:TP=-1.5:LRA=11")
        f.append(f"aresample={sample_rate}")

    if cfg.fade_in > 0:
        f.append(f"afade=t=in:st=0:d={cfg.fade_in:.3f}")
    if cfg.fade_out > 0 and out_duration > cfg.fade_out:
        start = max(0.0, out_duration - cfg.fade_out)
        f.append(f"afade=t=out:st={start:.3f}:d={cfg.fade_out:.3f}")

    f.append("alimiter=limit=0.97:level=false")
    return f


def _reverb_filters(amount: float, room_ms: int) -> list[str]:
    """Две каскадные ступени aecho — плотный хвост без внешнего IR-файла."""
    amount = float(np.clip(amount, 0.0, 1.0))
    room = max(40, int(room_ms))

    # ранние отражения (взаимно непериодичные задержки дают меньше "флэнжера")
    early_d = [int(room * k) for k in (0.17, 0.29, 0.41)]
    early_g = [round(amount * g, 3) for g in (0.55, 0.42, 0.33)]
    # хвост
    late_d = [int(room * k) for k in (0.61, 0.83, 1.0)]
    late_g = [round(amount * g, 3) for g in (0.45, 0.34, 0.26)]

    out_gain = round(1.0 - 0.22 * amount, 3)
    return [
        "aecho=0.86:{g}:{d}:{dec}".format(
            g=out_gain, d="|".join(map(str, early_d)), dec="|".join(map(str, early_g))
        ),
        "aecho=0.9:{g}:{d}:{dec}".format(
            g=out_gain, d="|".join(map(str, late_d)), dec="|".join(map(str, late_g))
        ),
    ]


def render_audio(
    src: str | Path,
    dst: str | Path,
    cfg: AudioCfg,
    info: MediaInfo,
    sample_rate: int = 44100,
) -> float:
    """Применяет эффекты и пишет WAV, который пойдёт и в анализ, и в видео.

    Возвращает фактическую длительность результата в секундах.
    """
    src_span = max(0.0, info.duration - cfg.start)
    if cfg.duration is not None:
        src_span = min(src_span, max(0.0, cfg.duration))
    if src_span <= 0:
        raise FFmpegError(
            tr("err.empty_span", start=cfg.start, duration=info.duration)
        )
    out_duration = src_span / max(cfg.speed, 1e-6)

    cmd = [_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    if cfg.start > 0:
        cmd += ["-ss", f"{cfg.start:.3f}"]
    cmd += ["-i", str(src)]
    if cfg.duration is not None:
        cmd += ["-t", f"{src_span:.3f}"]

    filters = build_audio_filters(cfg, sample_rate, out_duration)
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-ac", "2", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)]
    _run(cmd)

    return probe(dst).duration


def decode_mono(path: str | Path, sample_rate: int = 44100) -> np.ndarray:
    """Декодирует файл в моно float32 в диапазоне [-1, 1]."""
    proc = subprocess.run(
        [
            _tool("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-i", str(path), "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", "1", "-ar", str(sample_rate), "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-8:]
        raise FFmpegError(tr("err.decode_failed", details="\n  ".join(tail)))
    return np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32, copy=True)


# --------------------------------------------------------------------------- #
#  Кодирование видео
# --------------------------------------------------------------------------- #
class VideoEncoder:
    """Принимает RGB-кадры в stdin ffmpeg и склеивает их с готовым звуком."""

    def __init__(
        self,
        output: str | Path,
        audio_path: str | Path,
        video: VideoCfg,
        audio_bitrate: str | None = None,
    ) -> None:
        self.output = Path(output)
        self.output.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            _tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{video.width}x{video.height}", "-r", str(video.fps),
            "-i", "-",
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", video.preset, "-crf", str(video.crf),
            "-pix_fmt", video.pixel_format,
            "-c:a", "aac", "-b:a", audio_bitrate or video.audio_bitrate,
            "-movflags", "+faststart", "-shortest",
            str(self.output),
        ]
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._closed = False

    def write(self, frame: np.ndarray | bytes) -> None:
        """Пишет один кадр: массив (H, W, 3) uint8 или уже готовые байты."""
        assert self._proc.stdin is not None
        data = frame if isinstance(frame, (bytes, bytearray, memoryview)) else frame.tobytes()
        try:
            self._proc.stdin.write(data)
        except (BrokenPipeError, OSError) as e:
            raise FFmpegError(
                self._stderr_tail() or tr("err.pipe_closed", message=e)
            ) from e

    def _stderr_tail(self) -> str:
        if self._proc.stderr is None:
            return ""
        try:
            data = self._proc.stderr.read() or b""
        except Exception:
            return ""
        lines = data.decode("utf-8", "replace").strip().splitlines()[-12:]
        return "ffmpeg:\n  " + "\n  ".join(lines) if lines else ""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._proc.stdin:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
        err = self._proc.stderr.read() if self._proc.stderr else b""
        code = self._proc.wait()
        if code != 0:
            lines = err.decode("utf-8", "replace").strip().splitlines()[-12:]
            raise FFmpegError(
                tr("err.encode_failed", code=code, details="\n  ".join(lines))
            )

    def abort(self) -> None:
        """Аварийно завершает ffmpeg (например, по Ctrl+C)."""
        if self._closed:
            return
        self._closed = True
        try:
            self._proc.kill()
        except OSError:
            pass
        finally:
            self._proc.wait()

    def __enter__(self) -> VideoEncoder:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()


def extract_cover(audio_path: str | Path, dst: str | Path) -> Path | None:
    """Вытаскивает встроенную обложку из тегов, если она есть."""
    dst = Path(dst)
    proc = subprocess.run(
        [
            _tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(audio_path), "-an", "-vcodec", "copy", str(dst),
        ],
        capture_output=True,
    )
    if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
        return dst
    if dst.exists():
        dst.unlink(missing_ok=True)
    return None
