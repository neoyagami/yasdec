from __future__ import annotations

import threading
from collections import deque
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont
from PySide6.QtCore import QBuffer, QIODevice, QObject, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from .actions import elapsed_text
from .i18n import tr
from .model import KeyConfig
from .models import match_deck_model


class DeckBackend(QObject):
    key_pressed = Signal(int)
    connection_changed = Signal(str, bool)
    model_detected = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.deck = None
        self._pil_helper = None
        self._condition = threading.Condition()
        self._commands: deque[tuple] = deque()
        self._pending_spectrum: tuple | None = None
        self._worker: threading.Thread | None = None
        self._worker_stop = False
        self._spectrum_state: dict[int, tuple] = {}
        self._spectrum_native_cache: dict[tuple, bytes] = {}
        self._screen_spectrum_signature: tuple | None = None

    def connect_device(self) -> None:
        try:
            from StreamDeck.DeviceManager import DeviceManager
            from StreamDeck.ImageHelpers import PILHelper

            decks = DeviceManager().enumerate()
            if not decks:
                self.connection_changed.emit(tr("No device"), False)
                return
            self.deck = decks[0]
            self._pil_helper = PILHelper
            self.deck.open()
            self.deck.reset()
            self.deck.set_brightness(65)
            self.deck.set_key_callback(self._hardware_callback)
            self._start_worker()
            model_id = match_deck_model(self.deck.deck_type(), self.deck.key_count(), self.deck.key_layout())
            if model_id:
                self.model_detected.emit(model_id)
            self.connection_changed.emit(self.deck.deck_type(), True)
        except Exception as exc:
            self.deck = None
            self.connection_changed.emit(tr("No device: {error}", error=exc), False)

    def close(self) -> None:
        self._stop_worker()
        if self.deck:
            try:
                self.deck.reset()
                self.deck.close()
            except Exception:
                pass
            self.deck = None

    def render_space(self, keys: list[KeyConfig]) -> None:
        if not self.deck:
            return
        with self._condition:
            self._commands.clear()
            self._pending_spectrum = None
            self._spectrum_state.clear()
            self._screen_spectrum_signature = None
            self._commands.append(("space", deepcopy(keys)))
            self._condition.notify()

    def render_key(self, index: int, key: KeyConfig) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        with self._condition:
            self._commands.append(("key", index, deepcopy(key)))
            self._condition.notify()

    def render_spectrum(self, levels: list, stop_indices: set[int], colors: list, grid_size: int = 1) -> None:
        if not self.deck:
            return
        with self._condition:
            self._pending_spectrum = ("spectrum", deepcopy(levels), set(stop_indices), deepcopy(colors), max(1, min(3, grid_size)))
            self._condition.notify()

    def render_mini_spectrum(self, index: int, key: KeyConfig, levels: list[float]) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        with self._condition:
            self._pending_spectrum = ("mini-spectrum", index, deepcopy(key), list(levels))
            self._condition.notify()

    def render_vu(self, levels: list, colors: list) -> None:
        if not self.deck:
            return
        with self._condition:
            self._pending_spectrum = ("vu", deepcopy(levels), deepcopy(colors))
            self._condition.notify()

    def render_mini_vu(self, index: int, key: KeyConfig, levels: tuple[float, float]) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        with self._condition:
            self._pending_spectrum = ("mini-vu", index, deepcopy(key), tuple(levels))
            self._condition.notify()

    def _start_worker(self) -> None:
        self._worker_stop = False
        self._worker = threading.Thread(target=self._worker_loop, name="sdeck-hardware", daemon=True)
        self._worker.start()

    def _stop_worker(self) -> None:
        with self._condition:
            self._worker_stop = True
            self._commands.clear()
            self._pending_spectrum = None
            self._condition.notify_all()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        self._worker = None

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._worker_stop and not self._commands and self._pending_spectrum is None:
                    self._condition.wait()
                if self._worker_stop:
                    return
                command = self._commands.popleft() if self._commands else ("visual", *self._pending_spectrum)
                if command[0] == "visual":
                    self._pending_spectrum = None
            try:
                if command[0] == "key":
                    self._write_key(command[1], command[2])
                elif command[0] == "space":
                    self._write_space(command[1])
                elif command[0] == "visual" and command[1] == "mini-spectrum":
                    self._write_mini_spectrum(command[2], command[3], command[4])
                elif command[0] == "visual" and command[1] == "mini-vu":
                    self._write_mini_vu(command[2], command[3], command[4])
                elif command[0] == "visual" and command[1] == "vu":
                    self._write_vu(command[2], command[3])
                elif command[0] == "visual":
                    self._write_spectrum(command[2], command[3], command[4], command[5])
            except Exception as exc:
                self.connection_changed.emit(tr("Device error: {error}", error=exc), False)

    def _write_key(self, index: int, key: KeyConfig) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        size = self.deck.key_image_format()["size"]
        image = render_key_image(key, size)
        native = self._pil_helper.to_native_format(self.deck, image)
        with self.deck:
            self.deck.set_key_image(index, native)
        self._spectrum_state.pop(index, None)
        self._screen_spectrum_signature = None

    def _write_space(self, keys: list[KeyConfig]) -> None:
        if not self.deck:
            return
        size = self.deck.key_image_format()["size"]
        with self.deck:
            for index, key in enumerate(keys[: self.deck.key_count()]):
                image = render_key_image(key, size)
                native = self._pil_helper.to_native_format(self.deck, image)
                self.deck.set_key_image(index, native)
        self._spectrum_state.clear()
        self._screen_spectrum_signature = None

    def _write_mini_spectrum(self, index: int, key: KeyConfig, levels: list[float]) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        size = self.deck.key_image_format()["size"]
        image = render_mini_spectrum_key(key, levels, size)
        native = self._pil_helper.to_native_format(self.deck, image)
        with self.deck:
            self.deck.set_key_image(index, native)
        self._spectrum_state.pop(index, None)
        self._screen_spectrum_signature = None

    def _write_mini_vu(self, index: int, key: KeyConfig, levels: tuple[float, float]) -> None:
        if not self.deck or index >= self.deck.key_count():
            return
        size = self.deck.key_image_format()["size"]
        image = render_mini_vu_key(key, levels, size)
        native = self._pil_helper.to_native_format(self.deck, image)
        with self.deck:
            self.deck.set_key_image(index, native)
        self._spectrum_state.pop(index, None)
        self._screen_spectrum_signature = None

    def _write_vu(self, levels: list, colors: list) -> None:
        if not self.deck:
            return
        try:
            image_format = self.deck.key_image_format()
            size = image_format["size"]
            if self._supports_classic_full_screen(image_format):
                quantized = tuple(tuple(int(value >= 0.5) for value in spectrum_values(item)) for item in levels[:15])
                signature = ("vu", quantized, tuple(tuple(item) for item in colors[:15]))
                if signature == self._screen_spectrum_signature:
                    return
                image = render_classic_vu_screen(levels, colors)
                with BytesIO() as output:
                    image.rotate(180).save(output, "JPEG", quality=30, subsampling=2, optimize=True)
                    payload = output.getvalue()
                send_full_screen_image(self.deck, payload)
                self._screen_spectrum_signature = signature
                self._spectrum_state.clear()
                return
            with self.deck:
                for index, item in enumerate(levels[: self.deck.key_count()]):
                    values = tuple(int(value >= 0.5) for value in spectrum_values(item))
                    cell_colors = tuple(spectrum_colors(colors[index] if index < len(colors) else "#18f2a4", len(values)))
                    signature = ("vu", values, cell_colors)
                    if self._spectrum_state.get(index) == signature:
                        continue
                    cache_key = ("vu", size, values, cell_colors)
                    native = self._spectrum_native_cache.get(cache_key)
                    if native is None:
                        image = render_vu_key(values, size, cell_colors)
                        native = self._pil_helper.to_native_format(self.deck, image)
                        self._spectrum_native_cache[cache_key] = native
                    self.deck.set_key_image(index, native)
                    self._spectrum_state[index] = signature
        except Exception as exc:
            self.connection_changed.emit(tr("VU meter error: {error}", error=exc), False)

    def _write_spectrum(self, levels: list, stop_indices: set[int], colors: list, grid_size: int = 1) -> None:
        if not self.deck:
            return
        try:
            image_format = self.deck.key_image_format()
            size = image_format["size"]
            if self._supports_classic_full_screen(image_format):
                self._write_classic_screen_spectrum(levels, stop_indices, colors, grid_size)
                return
            # The first-generation 15-key deck uploads an uncompressed BMP in
            # two large HID reports per key. Binary cells avoid retransmitting
            # four intermediate fills for every level crossing.
            steps = 1 if str(image_format.get("format", "")).upper() == "BMP" else 3
            with self.deck:
                for index, level in enumerate(levels[: self.deck.key_count()]):
                    if index in stop_indices:
                        continue
                    cell_levels = spectrum_values(level)
                    cell_colors = spectrum_colors(colors[index] if index < len(colors) else "#42d3b3", len(cell_levels))
                    quantized = tuple(max(0, min(steps, round(value * steps))) for value in cell_levels)
                    signature = (quantized, tuple(cell_colors), grid_size)
                    if self._spectrum_state.get(index) == signature:
                        continue
                    cache_key = (size, steps, quantized, tuple(cell_colors), grid_size)
                    native = self._spectrum_native_cache.get(cache_key)
                    if native is None:
                        image = render_spectrum_key([value / steps for value in quantized], size, cell_colors, grid_size)
                        native = self._pil_helper.to_native_format(self.deck, image)
                        self._spectrum_native_cache[cache_key] = native
                    self.deck.set_key_image(index, native)
                    self._spectrum_state[index] = signature
        except Exception as exc:
            self.connection_changed.emit(tr("Analyzer error: {error}", error=exc), False)

    def _supports_classic_full_screen(self, image_format: dict) -> bool:
        return (
            self.deck is not None
            and self.deck.key_count() == 15
            and tuple(image_format.get("size", ())) == (72, 72)
            and str(image_format.get("format", "")).upper() == "JPEG"
            and hasattr(self.deck, "device")
        )

    def _write_classic_screen_spectrum(
        self, levels: list, stop_indices: set[int], colors: list, grid_size: int = 1
    ) -> None:
        assert self.deck is not None
        quantized = tuple(
            tuple(max(0, min(3, round(value * 3))) for value in spectrum_values(level))
            for level in levels[:15]
        )
        normalized_colors = tuple(
            tuple(spectrum_colors(colors[index] if index < len(colors) else "#42d3b3", len(values)))
            for index, values in enumerate(quantized)
        )
        signature = (quantized, normalized_colors, grid_size, tuple(sorted(stop_indices)))
        if signature == self._screen_spectrum_signature:
            return
        image = render_classic_spectrum_screen(levels, stop_indices, colors, grid_size)
        with BytesIO() as output:
            image.rotate(180).save(output, "JPEG", quality=20, subsampling=2, optimize=True)
            payload = output.getvalue()
        send_full_screen_image(self.deck, payload)
        self._screen_spectrum_signature = signature
        self._spectrum_state.clear()

    def _hardware_callback(self, _deck: object, key: int, state: bool) -> None:
        if state:
            self.key_pressed.emit(key)


def render_key_image(key: KeyConfig, size: tuple[int, int] = (96, 96)) -> Image.Image:
    background = pil_color(key.active_background_color if key.active else key.background_color, "#171b20")
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    icon_path = key.active_icon if key.active and key.active_icon else key.icon
    glyph = key.active_glyph if key.active and key.active_glyph else key.glyph
    icon_rendered = False
    if icon_path and Path(icon_path).is_file():
        try:
            reserved = 28 if key.label or key.show_timer else 10
            icon = load_icon_image(Path(icon_path), (size[0] - 16, size[1] - reserved))
            icon.thumbnail((size[0] - 16, size[1] - reserved), Image.Resampling.LANCZOS)
            if Path(icon_path).suffix.casefold() == ".svg":
                icon = tint_icon(icon, key.icon_color)
            image.paste(icon, ((size[0] - icon.width) // 2, 7), icon)
            icon_rendered = True
        except (OSError, ValueError):
            pass

    if glyph and not icon_rendered:
        reserved = 26 if key.label or key.show_timer else 8
        selected_font = glyph_font(max(24, int(size[0] * 0.48)))
        box = draw.textbbox((0, 0), glyph, font=selected_font)
        glyph_width, glyph_height = box[2] - box[0], box[3] - box[1]
        area_height = size[1] - reserved
        draw.text(
            ((size[0] - glyph_width) / 2, max(2, (area_height - glyph_height) / 2 - box[1])),
            glyph,
            font=selected_font,
            fill=pil_color(key.icon_color, "#ffffff"),
        )

    font = ImageFont.load_default(size=max(10, size[0] // 9))
    timer_font = ImageFont.load_default(size=max(9, size[0] // 10))
    timer = elapsed_text(key) if key.show_timer else ""
    if key.label:
        text = key.label[:18]
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((size[0] - (box[2] - box[0])) / 2, size[1] - 25), text, font=font, fill=pil_color(key.text_color, "#ffffff"))
    if timer:
        box = draw.textbbox((0, 0), timer, font=timer_font)
        draw.text(((size[0] - (box[2] - box[0])) / 2, size[1] - 12), timer, font=timer_font, fill=pil_color(key.text_color, "#ffffff"))
    return image


def render_mini_spectrum_key(
    key: KeyConfig, levels: list[float], size: tuple[int, int] = (96, 96)
) -> Image.Image:
    preview = deepcopy(key)
    preview.active = False
    preview.icon = preview.active_icon = ""
    preview.glyph = preview.active_glyph = ""
    image = render_key_image(preview, size)
    draw = ImageDraw.Draw(image)
    count = max(1, len(levels))
    left, right = 7, size[0] - 7
    top = 7
    bottom = size[1] - (27 if key.label or key.show_timer else 7)
    gap = 2
    width = max(1, (right - left - gap * (count - 1)) // count)
    color = pil_color(key.icon_color, "#42d3b3")
    for index, level in enumerate(levels):
        height = max(1, round((bottom - top) * max(0.0, min(1.0, level))))
        x = left + index * (width + gap)
        draw.rounded_rectangle((x, bottom - height, x + width - 1, bottom), radius=1, fill=color)
    return image


def interpolate_color(start: str, end: str, position: float) -> str:
    first = pil_color(start, "#18f2a4")
    last = pil_color(end, "#ff3b81")
    ratio = max(0.0, min(1.0, position))
    return "#" + "".join(f"{round(a + (b - a) * ratio):02x}" for a, b in zip(first, last))


def vu_gradient(start: str, end: str, count: int) -> list[str]:
    return [interpolate_color(start, end, index / max(1, count - 1)) for index in range(max(1, count))]


def render_mini_vu_key(
    key: KeyConfig, levels: tuple[float, float], size: tuple[int, int] = (96, 96)
) -> Image.Image:
    preview = deepcopy(key)
    preview.active = False
    preview.icon = preview.active_icon = ""
    preview.glyph = preview.active_glyph = ""
    image = render_key_image(preview, size)
    draw = ImageDraw.Draw(image)
    count = 8
    colors = vu_gradient(key.vu_color_start, key.vu_color_end, count)
    left, right = 6, size[0] - 6
    top = 8
    bottom = size[1] - (28 if key.label or key.show_timer else 8)
    lane_gap = 5
    lane_height = max(4, (bottom - top - lane_gap) // 2)
    cell_gap = 2
    cell_width = max(2, (right - left - cell_gap * (count - 1)) // count)
    for channel, level in enumerate(levels):
        y0 = top + channel * (lane_height + lane_gap)
        active = round(max(0.0, min(1.0, level)) * count)
        for index in range(count):
            x0 = left + index * (cell_width + cell_gap)
            fill = colors[index] if index < active else "#101716"
            draw.rounded_rectangle((x0, y0, x0 + cell_width - 1, y0 + lane_height), radius=1, fill=fill)
    return image


def render_vu_key(levels: object, size: tuple[int, int], colors: object) -> Image.Image:
    values = spectrum_values(levels)
    cell_colors = spectrum_colors(colors, len(values))
    image = Image.new("RGB", size, "#030606")
    draw = ImageDraw.Draw(image)
    count = max(1, len(values))
    margin = max(3, round(min(size) * 0.055))
    gap = max(2, round(min(size) * 0.04))
    width = (size[0] - margin * 2 - gap * (count - 1)) / count
    for index in range(count):
        x0 = round(margin + index * (width + gap))
        x1 = round(x0 + width - 1)
        fill = cell_colors[index] if values[index] >= 0.5 else "#101716"
        draw.rounded_rectangle((x0, margin, x1, size[1] - margin - 1), radius=max(1, round(width * 0.13)), fill=fill)
    return image


def render_classic_vu_screen(levels: list, colors: list) -> Image.Image:
    screen = Image.new("RGB", (480, 272), "#020404")
    for index in range(15):
        x = 11 + (index % 5) * 97
        y = 5 + (index // 5) * 97
        values = levels[index] if index < len(levels) else [0.0, 0.0, 0.0]
        cell_colors = colors[index] if index < len(colors) else ["#18f2a4"] * 3
        screen.paste(render_vu_key(values, (72, 72), cell_colors), (x, y))
    return screen


def pil_color(value: str, fallback: str) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb(value)
    except ValueError:
        return ImageColor.getrgb(fallback)


def tint_icon(icon: Image.Image, color: str) -> Image.Image:
    tinted = Image.new("RGBA", icon.size, pil_color(color, "#ffffff") + (255,))
    tinted.putalpha(icon.getchannel("A"))
    return tinted


def load_icon_image(path: Path, maximum: tuple[int, int]) -> Image.Image:
    if path.suffix.casefold() != ".svg":
        return Image.open(path).convert("RGBA")
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(tr("Invalid SVG: {path}", path=path))
    width, height = maximum
    qimage = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied)
    qimage.fill(0)
    painter = QPainter(qimage)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    qimage.save(buffer, "PNG")
    return Image.open(BytesIO(bytes(buffer.data()))).convert("RGBA")


def glyph_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/google-noto/NotoSansSymbols2-Regular.ttf",
        "/usr/share/fonts/google-noto-vf/NotoSansSymbols[wght].ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=max(10, size // 2))


def spectrum_values(value: object) -> list[float]:
    values = value if isinstance(value, (list, tuple)) else [value]
    result: list[float] = []
    for item in values:
        try:
            result.append(max(0.0, min(1.0, float(item))))
        except (TypeError, ValueError):
            result.append(0.0)
    return result or [0.0]


def spectrum_colors(value: object, count: int) -> list[str]:
    values = [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)]
    values = values or ["#42d3b3"]
    return [values[min(index, len(values) - 1)] for index in range(count)]


def render_spectrum_key(
    level: object,
    size: tuple[int, int],
    color: object = "#42d3b3",
    grid_size: int = 1,
) -> Image.Image:
    values = spectrum_values(level)
    colors = spectrum_colors(color, len(values))
    image = Image.new("RGB", size, "#101419")
    draw = ImageDraw.Draw(image)
    grid_size = max(1, min(3, int(grid_size)))
    if grid_size == 1:
        height = int((size[1] - 10) * values[0])
        draw.rounded_rectangle((7, size[1] - 5 - height, size[0] - 7, size[1] - 5), radius=4, fill=colors[0])
        return image

    margin = max(4, round(min(size) * 0.09))
    gap = max(2, round(min(size) * 0.045))
    cell_width = (size[0] - margin * 2 - gap * (grid_size - 1)) / grid_size
    cell_height = (size[1] - margin * 2 - gap * (grid_size - 1)) / grid_size
    for index in range(grid_size * grid_size):
        row, column = divmod(index, grid_size)
        x0 = round(margin + column * (cell_width + gap))
        y0 = round(margin + row * (cell_height + gap))
        x1 = round(x0 + cell_width - 1)
        y1 = round(y0 + cell_height - 1)
        lit = values[index] >= 0.5 if index < len(values) else False
        fill = colors[index] if lit and index < len(colors) else "#18211f"
        draw.rounded_rectangle((x0, y0, x1, y1), radius=max(1, round(min(cell_width, cell_height) * 0.12)), fill=fill)
    return image


def render_classic_spectrum_screen(
    levels: list, stop_indices: set[int], colors: list, grid_size: int = 1
) -> Image.Image:
    screen = Image.new("RGB", (480, 272), "#050607")
    for index in range(15):
        x = 11 + (index % 5) * 97
        y = 5 + (index // 5) * 97
        if index in stop_indices:
            tile = Image.new("RGB", (72, 72), "#8f2f35")
            draw = ImageDraw.Draw(tile)
            draw.rounded_rectangle((23, 23, 49, 49), radius=3, fill="white")
        else:
            level = levels[index] if index < len(levels) else 0.0
            color = colors[index] if index < len(colors) else "#42d3b3"
            values = spectrum_values(level)
            if grid_size == 1:
                values = [round(values[0] * 3) / 3]
            tile = render_spectrum_key(values, (72, 72), color, grid_size)
        screen.paste(tile, (x, y))
    return screen


def send_full_screen_image(deck: object, image: bytes) -> None:
    report_length = int(getattr(deck, "IMAGE_REPORT_LENGTH", 1024))
    payload_length = report_length - 8
    page = 0
    offset = 0
    while offset < len(image):
        chunk = image[offset : offset + payload_length]
        done = offset + len(chunk) >= len(image)
        header = bytes((0x02, 0x08, 0x00, int(done), len(chunk) & 0xFF, len(chunk) >> 8, page & 0xFF, page >> 8))
        deck.device.write(header + chunk + bytes(report_length - len(header) - len(chunk)))
        offset += len(chunk)
        page += 1
