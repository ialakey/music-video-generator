"""Запуск пакета: `python -m musicvideo ...`."""
from __future__ import annotations

import multiprocessing as mp

from .cli import main

if __name__ == "__main__":
    mp.freeze_support()  # нужно для spawn-воркеров на Windows
    raise SystemExit(main())
