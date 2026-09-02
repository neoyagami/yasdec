import unittest

from PIL import Image

from sdeck.hardware import DeckBackend, render_classic_spectrum_screen, render_key_image, render_mini_spectrum_key, render_mini_vu_key, render_spectrum_key, render_vu_key, send_full_screen_image, tint_icon, vu_gradient
from sdeck.model import KeyConfig


class FakeDeck:
    def __init__(self, image_format: str = "JPEG") -> None:
        self.images: list[tuple[int, bytes]] = []
        self.image_format = image_format

    def key_count(self) -> int:
        return 4

    def key_image_format(self) -> dict:
        return {"size": (72, 72), "format": self.image_format}

    def set_key_image(self, index: int, image: bytes) -> None:
        self.images.append((index, image))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakePILHelper:
    @staticmethod
    def to_native_format(_deck, image) -> bytes:
        return image.tobytes()


class FakeTransport:
    def __init__(self) -> None:
        self.reports: list[bytes] = []

    def write(self, report: bytes) -> None:
        self.reports.append(report)


class HardwareSpectrumTests(unittest.TestCase):
    def test_vu_segments_use_full_height_and_neon_gradient(self) -> None:
        colors = vu_gradient("#00ff80", "#ff0080", 3)
        image = render_vu_key([1.0, 0.0, 1.0], (72, 72), colors)
        self.assertEqual(image.getpixel((14, 36)), (0, 255, 128))
        self.assertEqual(image.getpixel((36, 36)), (16, 23, 22))
        self.assertEqual(image.getpixel((58, 36)), (255, 0, 128))
        self.assertEqual(image.getpixel((14, 7)), (0, 255, 128))

    def test_unchanged_vu_keys_are_not_resent(self) -> None:
        backend = DeckBackend()
        deck = FakeDeck()
        backend.deck = deck
        backend._pil_helper = FakePILHelper
        levels = [[1.0, 0.0, 0.0] for _ in range(4)]
        colors = [["#18f2a4"] * 3 for _ in range(4)]
        backend._write_vu(levels, colors)
        self.assertEqual(len(deck.images), 4)
        backend._write_vu(levels, colors)
        self.assertEqual(len(deck.images), 4)
        levels[1][1] = 1.0
        backend._write_vu(levels, colors)
        self.assertEqual(len(deck.images), 5)

    def test_mini_vu_preview_has_two_independent_lanes(self) -> None:
        key = KeyConfig(label="VU", vu_color_start="#00ff80", vu_color_end="#ff0080")
        image = render_mini_vu_key(key, (1.0, 0.25), (72, 72))
        top_lit = sum(1 for x in range(72) if image.getpixel((x, 12)) != (16, 23, 22))
        bottom_lit = sum(1 for x in range(72) if image.getpixel((x, 34)) != (16, 23, 22))
        self.assertGreater(top_lit, bottom_lit)

    def test_unchanged_spectrum_cells_are_not_resent(self) -> None:
        backend = DeckBackend()
        deck = FakeDeck()
        backend.deck = deck
        backend._pil_helper = FakePILHelper
        colors = ["#42d3b3"] * 4
        backend._write_spectrum([0.0, 0.4, 0.7, 1.0], set(), colors)
        self.assertEqual(len(deck.images), 4)
        backend._write_spectrum([0.0, 0.4, 0.7, 1.0], set(), colors)
        self.assertEqual(len(deck.images), 4)
        backend._write_spectrum([0.0, 0.8, 0.7, 1.0], set(), colors)
        self.assertEqual(len(deck.images), 5)

    def test_bmp_decks_only_send_binary_level_crossings(self) -> None:
        backend = DeckBackend()
        deck = FakeDeck("BMP")
        backend.deck = deck
        backend._pil_helper = FakePILHelper
        colors = ["#42d3b3"] * 4
        backend._write_spectrum([0.1, 0.6, 0.2, 0.9], set(), colors)
        self.assertEqual(len(deck.images), 4)
        backend._write_spectrum([0.4, 0.8, 0.3, 1.0], set(), colors)
        self.assertEqual(len(deck.images), 4)
        backend._write_spectrum([0.7, 0.8, 0.3, 1.0], set(), colors)
        self.assertEqual(len(deck.images), 5)

    def test_classic_screen_layout_uses_official_key_coordinates(self) -> None:
        image = render_classic_spectrum_screen([1.0] * 15, {2}, ["#42d3b3"] * 15)
        self.assertEqual(image.size, (480, 272))
        self.assertEqual(image.getpixel((11, 5)), (16, 20, 25))
        self.assertEqual(image.getpixel((11 + 2 * 97 + 36, 5 + 36)), (255, 255, 255))

    def test_three_by_three_lcd_grid_has_nine_separate_cells(self) -> None:
        values = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        image = render_spectrum_key(values, (72, 72), ["#42d3b3"] * 9, 3)
        centers = (15, 36, 57)
        sampled = [image.getpixel((x, y)) for y in centers for x in centers]
        self.assertEqual(sampled[::2], [(66, 211, 179)] * 5)
        self.assertEqual(sampled[1::2], [(24, 33, 31)] * 4)

    def test_lcd_grid_cache_only_resends_changed_keys(self) -> None:
        backend = DeckBackend()
        deck = FakeDeck()
        backend.deck = deck
        backend._pil_helper = FakePILHelper
        levels = [[0.0] * 9 for _ in range(4)]
        colors = [["#42d3b3"] * 9 for _ in range(4)]
        backend._write_spectrum(levels, set(), colors, 3)
        self.assertEqual(len(deck.images), 4)
        backend._write_spectrum(levels, set(), colors, 3)
        self.assertEqual(len(deck.images), 4)
        levels[2][8] = 1.0
        backend._write_spectrum(levels, set(), colors, 3)
        self.assertEqual(len(deck.images), 5)

    def test_full_screen_command_chunks_image(self) -> None:
        deck = FakeDeck()
        deck.IMAGE_REPORT_LENGTH = 1024
        deck.device = FakeTransport()
        send_full_screen_image(deck, bytes(2500))
        self.assertEqual(len(deck.device.reports), 3)
        self.assertTrue(all(len(report) == 1024 for report in deck.device.reports))
        self.assertEqual(deck.device.reports[0][:4], bytes((0x02, 0x08, 0x00, 0x00)))
        self.assertEqual(deck.device.reports[-1][:4], bytes((0x02, 0x08, 0x00, 0x01)))

    def test_key_background_colors_are_rendered(self) -> None:
        key = KeyConfig(background_color="#123456", active_background_color="#654321")
        self.assertEqual(render_key_image(key, (72, 72)).getpixel((0, 0)), (18, 52, 86))
        key.active = True
        self.assertEqual(render_key_image(key, (72, 72)).getpixel((0, 0)), (101, 67, 33))

    def test_icon_tint_preserves_alpha(self) -> None:
        source = Image.new("RGBA", (2, 2), (255, 255, 255, 0))
        source.putpixel((1, 1), (255, 255, 255, 128))
        tinted = tint_icon(source, "#ff0080")
        self.assertEqual(tinted.getpixel((1, 1)), (255, 0, 128, 128))
        self.assertEqual(tinted.getpixel((0, 0))[3], 0)

    def test_mini_spectrum_replaces_icon_with_multiple_bars(self) -> None:
        key = KeyConfig(background_color="#101010", icon_color="#00ff00")
        image = render_mini_spectrum_key(key, [0.2, 0.5, 1.0], (72, 72))
        green_pixels = sum(1 for pixel in image.get_flattened_data() if pixel == (0, 255, 0))
        self.assertGreater(green_pixels, 20)



if __name__ == "__main__":
    unittest.main()
