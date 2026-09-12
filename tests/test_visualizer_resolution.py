import unittest
from itertools import groupby
from types import SimpleNamespace
from unittest.mock import Mock

from sdeck.hardware import render_spectrum_key, render_vu_key
from sdeck.model import KeyConfig
from sdeck.window import MainWindow


class VisualizerResolutionTests(unittest.TestCase):
    def test_response_settings_round_trip_and_defaults(self):
        key = KeyConfig(spectrum_gain_db=12, spectrum_fall_ms=1200)
        restored = KeyConfig.from_dict(key.to_dict())
        self.assertEqual((restored.spectrum_gain_db, restored.spectrum_fall_ms), (12, 1200))
        default = KeyConfig.from_dict({})
        self.assertEqual((default.spectrum_gain_db, default.spectrum_fall_ms), (0, 800))
        self.assertFalse(default.spectrum_auto_scale)

    def test_resolution_settings_round_trip_and_old_defaults(self):
        key = KeyConfig(spectrum_grid_size=6, vu_segments=8)
        restored = KeyConfig.from_dict(key.to_dict())
        self.assertEqual((restored.spectrum_grid_size, restored.vu_segments), (6, 8))
        self.assertEqual(KeyConfig.from_dict({}).vu_segments, 3)
        for value, expected in ((None, 3), ("bad", 3), (0, 3), (100, 8)):
            self.assertEqual(KeyConfig.from_dict({"vu_segments": value}).vu_segments, expected)

    def test_dense_blocks_keep_dark_gaps_at_supported_key_sizes(self):
        lit = (0, 255, 128)
        for size in (72, 80, 96, 120):
            for count in range(3, 9):
                with self.subTest(kind="vu", size=size, count=count):
                    image = render_vu_key([1.0] * count, (size, size), ["#00ff80"] * count)
                    runs = [(on, len(list(pixels))) for on, pixels in groupby(
                        image.getpixel((x, size // 2)) == lit for x in range(size))]
                    self.assertEqual(sum(on for on, _ in runs), count)
                    self.assertTrue(all(length >= 2 for on, length in runs if not on))
            for grid in range(2, 7):
                with self.subTest(kind="spectrum", size=size, grid=grid):
                    image = render_spectrum_key([1.0] * (grid * grid), (size, size),
                                                ["#00ff80"] * (grid * grid), grid)
                    margin = max(4, round(size * 0.09))
                    gap = max(2, round(size * 0.045))
                    width = (size - 2 * margin - gap * (grid - 1)) / grid
                    center = round(margin + width / 2)
                    for vertical in (False, True):
                        runs = [(on, len(list(pixels))) for on, pixels in groupby(
                            image.getpixel((center, x) if vertical else (x, center)) == lit
                            for x in range(size))]
                        self.assertEqual(sum(on for on, _ in runs), grid)
                        self.assertTrue(all(length >= 2 for on, length in runs if not on))

    def test_vu_fullscreen_uses_configured_resolution_for_both_channels(self):
        for count in (3, 8):
            with self.subTest(count=count):
                window = SimpleNamespace(
                    runner=SimpleNamespace(vu_fullscreen=True, vu_key=KeyConfig(vu_segments=count)),
                    config=SimpleNamespace(key_count=15, columns=5,
                                           current=lambda: SimpleNamespace(keys=[KeyConfig()] * 15)),
                    key_buttons=[Mock() for _ in range(15)], deck=Mock(), vu_levels=(1.0, 0.5),
                )
                MainWindow._draw_vu(window)
                levels, colors = window.deck.render_vu.call_args.args
                self.assertTrue(all(len(row) == count for row in levels + colors))
                self.assertEqual(sum(map(sum, levels[:5])), 5 * count)
                self.assertEqual(sum(map(sum, levels[5:10])), 0)
                self.assertEqual(sum(map(sum, levels[10:])), round(5 * count / 2))
