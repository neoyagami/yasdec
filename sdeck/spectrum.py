from __future__ import annotations

import math
import shutil
import struct
import subprocess
import threading

from PySide6.QtCore import QObject, Signal

from .i18n import tr
from .process_environment import external_process_environment


class SpectrumController(QObject):
    levels_changed = Signal(object)
    status = Signal(str, bool)
    ended = Signal()

    SAMPLE_RATE = 16_000
    SAMPLE_COUNT = 1024

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._peak = 1.0

    def start(self, device: str, band_count: int) -> bool:
        self.stop()
        if not device:
            self.status.emit(tr("Select a valid audio input or output"), False)
            return False
        parec = shutil.which("parec")
        if not parec:
            self.status.emit(tr("parec was not found"), False)
            return False
        try:
            self._process = subprocess.Popen(
                capture_command(parec, device, self.SAMPLE_RATE),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                env=external_process_environment(),
            )
        except OSError as exc:
            self.status.emit(tr("Could not start the analyzer: {error}", error=exc), False)
            return False
        self._stop.clear()
        self._peak = 1.0
        self._thread = threading.Thread(target=self._capture, args=(max(1, band_count),), name="sdeck-spectrum", daemon=True)
        self._thread.start()
        self.status.emit(tr("Spectrum analyzer active"), True)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._process = None
        self._thread = None

    def _capture(self, band_count: int) -> None:
        assert self._process and self._process.stdout
        byte_count = self.SAMPLE_COUNT * 2
        frequencies = log_frequencies(band_count, 55.0, 7000.0)
        coefficients = [2.0 * math.cos(2.0 * math.pi * frequency / self.SAMPLE_RATE) for frequency in frequencies]
        while not self._stop.is_set():
            data = read_exact(self._process.stdout, byte_count)
            if len(data) != byte_count:
                break
            samples = struct.unpack(f"<{self.SAMPLE_COUNT}h", data)
            powers = [goertzel(samples, coefficient) for coefficient in coefficients]
            frame_peak = max(powers, default=1.0)
            self._peak = max(frame_peak, self._peak * 0.94, 1.0)
            levels = [min(1.0, max(0.0, math.log10(1.0 + power) / math.log10(1.0 + self._peak))) for power in powers]
            self.levels_changed.emit(levels)
        if not self._stop.is_set():
            self.status.emit(tr("Analyzer capture ended"), False)
            self.ended.emit()

    def close(self) -> None:
        self.stop()


class StereoVuController(QObject):
    levels_changed = Signal(object)
    status = Signal(str, bool)
    ended = Signal()

    SAMPLE_RATE = 16_000
    SAMPLE_FRAMES = 640

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._levels = [0.0, 0.0]

    def start(self, device: str) -> bool:
        self.stop()
        if not device:
            self.status.emit(tr("Select a valid audio input or output"), False)
            return False
        parec = shutil.which("parec")
        if not parec:
            self.status.emit(tr("parec was not found"), False)
            return False
        try:
            self._process = subprocess.Popen(
                capture_command(parec, device, self.SAMPLE_RATE, channels=2),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                env=external_process_environment(),
            )
        except OSError as exc:
            self.status.emit(tr("Could not start the VU meter: {error}", error=exc), False)
            return False
        self._stop.clear()
        self._levels = [0.0, 0.0]
        self._thread = threading.Thread(target=self._capture, name="yasdec-stereo-vu", daemon=True)
        self._thread.start()
        self.status.emit(tr("Stereo VU meter active"), True)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._process = None
        self._thread = None

    def _capture(self) -> None:
        assert self._process and self._process.stdout
        byte_count = self.SAMPLE_FRAMES * 2 * 2
        while not self._stop.is_set():
            data = read_exact(self._process.stdout, byte_count)
            if len(data) != byte_count:
                break
            samples = struct.unpack(f"<{self.SAMPLE_FRAMES * 2}h", data)
            current = stereo_vu_levels(samples)
            for channel in range(2):
                self._levels[channel] = current[channel] if current[channel] >= self._levels[channel] else self._levels[channel] * 0.82
            self.levels_changed.emit(tuple(self._levels))
        if not self._stop.is_set():
            self.status.emit(tr("VU meter capture ended"), False)
            self.ended.emit()

    def close(self) -> None:
        self.stop()


def stereo_vu_levels(samples: tuple[int, ...]) -> tuple[float, float]:
    """Map interleaved stereo PCM to a -48 dBFS..0 dBFS meter range."""
    if len(samples) < 2:
        return (0.0, 0.0)
    result: list[float] = []
    for channel in range(2):
        values = samples[channel::2]
        rms = math.sqrt(sum(float(value) * value for value in values) / max(1, len(values)))
        dbfs = 20.0 * math.log10(max(1.0, rms) / 32768.0)
        result.append(max(0.0, min(1.0, (dbfs + 48.0) / 48.0)))
    return (result[0], result[1])


def log_frequencies(count: int, low: float, high: float) -> list[float]:
    if count == 1:
        return [(low + high) / 2]
    ratio = high / low
    return [low * ratio ** (index / (count - 1)) for index in range(count)]


def capture_command(parec: str, device: str, sample_rate: int, channels: int = 1) -> list[str]:
    return [
        parec,
        "--raw",
        "--format=s16le",
        f"--rate={sample_rate}",
        f"--channels={max(1, channels)}",
        "--latency-msec=40",
        "--process-time-msec=40",
        f"--device={device}",
    ]


def goertzel(samples: tuple[int, ...], coefficient: float) -> float:
    previous = previous_two = 0.0
    count = len(samples)
    for index, sample in enumerate(samples):
        window = 0.5 - 0.5 * math.cos(2.0 * math.pi * index / max(1, count - 1))
        current = sample * window + coefficient * previous - previous_two
        previous_two, previous = previous, current
    return max(0.0, previous_two * previous_two + previous * previous - coefficient * previous * previous_two)


def read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)
