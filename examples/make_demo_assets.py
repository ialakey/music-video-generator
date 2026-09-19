"""Генерирует демо-трек и картинку, чтобы попробовать генератор без своих файлов.

    python examples/make_demo_assets.py
    python -m musicvideo examples/demo.wav -i examples/demo.jpg -p aesthetic
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SR = 44100
OUT = Path(__file__).resolve().parent


def make_track(seconds: float = 20.0, bpm: float = 84.0) -> np.ndarray:
    """Простой бит: кик, бас-линия, аккорд и хэты — чтобы спектр был живым."""
    n = int(SR * seconds)
    t = np.arange(n) / SR
    beat = 60.0 / bpm
    mix = np.zeros(n, dtype=np.float32)

    # кик: синус с быстро падающей частотой и огибающей
    for i in range(int(seconds / beat)):
        start = int(i * beat * SR)
        length = min(int(0.35 * SR), n - start)
        if length <= 0:
            break
        local = np.arange(length) / SR
        freq = 120.0 * np.exp(-local * 24.0) + 42.0
        env = np.exp(-local * 9.0)
        mix[start:start + length] += (np.sin(2 * np.pi * freq * local) * env).astype(np.float32)

    # бас: смена нот каждые два такта
    notes = [55.0, 55.0, 73.42, 65.41]
    bass = np.zeros(n, dtype=np.float32)
    for i in range(int(seconds / (beat * 2)) + 1):
        start = int(i * beat * 2 * SR)
        length = min(int(beat * 2 * SR), n - start)
        if length <= 0:
            break
        local = np.arange(length) / SR
        f = notes[i % len(notes)]
        env = np.minimum(1.0, local * 30.0) * np.exp(-local * 1.2)
        bass[start:start + length] += (np.sin(2 * np.pi * f * local) * env * 0.5).astype(np.float32)
    mix += bass

    # аккорд-пэд
    for f in (220.0, 277.18, 329.63, 440.0):
        mix += (np.sin(2 * np.pi * f * t) * 0.07 * (0.6 + 0.4 * np.sin(2 * np.pi * t / 6))).astype(np.float32)

    # хэты на каждую восьмую
    rng = np.random.default_rng(3)
    for i in range(int(seconds / (beat / 2))):
        start = int(i * beat / 2 * SR)
        length = min(int(0.05 * SR), n - start)
        if length <= 0:
            break
        local = np.arange(length) / SR
        noise = rng.normal(0, 1, length) * np.exp(-local * 90.0)
        mix[start:start + length] += (noise * 0.12).astype(np.float32)

    mix *= np.minimum(1.0, t * 2.0) * np.minimum(1.0, (seconds - t) * 1.5)
    peak = float(np.max(np.abs(mix))) or 1.0
    return (mix / peak * 0.89).astype(np.float32)


def write_wav(path: Path, mono: np.ndarray) -> None:
    data = (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2")
    stereo = np.repeat(data[:, None], 2, axis=1).tobytes()
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(stereo)


def make_image(path: Path, size: tuple[int, int] = (1600, 1600)) -> None:
    """Абстрактная картинка-«обложка» из мягких цветных пятен."""
    w, h = size
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = xx / w, yy / h

    arr = np.zeros((h, w, 3), dtype=np.float32)
    palette = [(255, 92, 128), (120, 80, 255), (46, 214, 214), (255, 190, 90)]
    for (r, g, b) in palette:
        cx, cy = rng.uniform(0.15, 0.85, 2)
        spread = rng.uniform(0.18, 0.4)
        blob = np.exp(-(((nx - cx) ** 2 + (ny - cy) ** 2) / (2 * spread ** 2)))
        arr += blob[..., None] * np.array([r, g, b], dtype=np.float32)

    arr *= 0.75
    arr += (ny[..., None] * -60.0)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    img.filter(ImageFilter.GaussianBlur(6)).save(path, quality=92)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write_wav(OUT / "demo.wav", make_track())
    make_image(OUT / "demo.jpg")
    print(f"Готово: {OUT / 'demo.wav'}, {OUT / 'demo.jpg'}")
