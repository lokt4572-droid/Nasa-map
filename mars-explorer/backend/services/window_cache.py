"""Bounded in-memory cache of remote raster window reads.

Remote DTMs (Cloud-Optimized GeoTIFFs) are read over HTTP; the same window is often requested
again (re-opening a view, a profile, a route and its return). Caching the decoded window keeps
those repeats from downloading the same blocks again. Values are exactly what GDAL returned; the
cache never changes them. Local files are not cached (the disk is fast). Thread-safe, LRU,
bounded by bytes (settings.REMOTE_WINDOW_CACHE_MB, default 256).
"""
from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np
from django.conf import settings

from services import remote_raster

_lock = threading.Lock()
_items: OrderedDict[tuple, np.ma.MaskedArray] = OrderedDict()
_bytes = 0
stats = {"hits": 0, "misses": 0}


def _limit() -> int:
    return int(getattr(settings, "REMOTE_WINDOW_CACHE_MB", 256)) * 1024 * 1024


def clear() -> None:
    global _bytes
    with _lock:
        _items.clear()
        _bytes = 0
        stats.update(hits=0, misses=0)


def read(src, path, window, out_shape) -> np.ma.MaskedArray:
    """``src.read(1, window=window, out_shape=out_shape, masked=True)`` with caching for remote files."""
    global _bytes
    if not remote_raster.is_remote(path):
        return src.read(1, window=window, out_shape=out_shape, masked=True)
    key = (str(path), int(window.col_off), int(window.row_off), int(window.width), int(window.height), tuple(int(v) for v in out_shape))
    with _lock:
        hit = _items.get(key)
        if hit is not None:
            _items.move_to_end(key)
            stats["hits"] += 1
            return hit.copy()
    arr = src.read(1, window=window, out_shape=out_shape, masked=True)
    size = arr.data.nbytes + np.ma.getmaskarray(arr).nbytes
    with _lock:
        stats["misses"] += 1
        if size <= _limit():
            _items[key] = arr.copy()
            _bytes += size
            while _bytes > _limit() and _items:
                _, old = _items.popitem(last=False)
                _bytes -= old.data.nbytes + np.ma.getmaskarray(old).nbytes
    return arr
