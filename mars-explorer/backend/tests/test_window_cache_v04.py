"""Remote window cache: exact values, bounded memory, local files untouched."""
import numpy as np
from django.test import SimpleTestCase, override_settings
from rasterio.windows import Window

from services import window_cache

REMOTE = "https://astrogeo-ard.s3-us-west-2.amazonaws.com/x_dtm.tif"


class FakeSrc:
    def __init__(self):
        self.calls = 0

    def read(self, band, window, out_shape, masked):
        self.calls += 1
        a = np.ma.masked_array(np.arange(out_shape[0] * out_shape[1], dtype="float32").reshape(out_shape) + window.col_off)
        a[0, 0] = np.ma.masked
        return a


class WindowCacheTests(SimpleTestCase):
    def setUp(self):
        window_cache.clear()

    def test_hit_returns_identical_values_without_reading(self):
        src = FakeSrc()
        a = window_cache.read(src, REMOTE, Window(10, 20, 30, 40), (8, 8))
        b = window_cache.read(src, REMOTE, Window(10, 20, 30, 40), (8, 8))
        self.assertEqual(src.calls, 1)
        np.testing.assert_array_equal(a.filled(np.nan), b.filled(np.nan))
        self.assertTrue(np.ma.getmaskarray(b)[0, 0])  # NoData mask preserved
        self.assertEqual(window_cache.stats, {"hits": 1, "misses": 1})

    def test_callers_cannot_corrupt_the_cache(self):
        src = FakeSrc()
        a = window_cache.read(src, REMOTE, Window(0, 0, 4, 4), (4, 4))
        a[1, 1] = -999
        b = window_cache.read(src, REMOTE, Window(0, 0, 4, 4), (4, 4))
        self.assertNotEqual(float(b[1, 1]), -999.0)

    def test_different_windows_or_shapes_are_different_entries(self):
        src = FakeSrc()
        window_cache.read(src, REMOTE, Window(0, 0, 4, 4), (4, 4))
        window_cache.read(src, REMOTE, Window(1, 0, 4, 4), (4, 4))
        window_cache.read(src, REMOTE, Window(0, 0, 4, 4), (2, 2))
        self.assertEqual(src.calls, 3)

    def test_local_files_are_not_cached(self):
        src = FakeSrc()
        window_cache.read(src, "C:/data/dem.tif", Window(0, 0, 4, 4), (4, 4))
        window_cache.read(src, "C:/data/dem.tif", Window(0, 0, 4, 4), (4, 4))
        self.assertEqual(src.calls, 2)

    @override_settings(REMOTE_WINDOW_CACHE_MB=1)
    def test_memory_bound_evicts_oldest(self):
        src = FakeSrc()
        for k in range(4):  # 4 x (512*512*4 B data + mask) > 1 MB
            window_cache.read(src, REMOTE, Window(k, 0, 512, 512), (512, 512))
        self.assertLessEqual(window_cache._bytes, 1024 * 1024)
        window_cache.read(src, REMOTE, Window(0, 0, 512, 512), (512, 512))  # oldest was evicted
        self.assertEqual(src.calls, 5)
