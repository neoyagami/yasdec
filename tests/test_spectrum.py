import math
import unittest

from sdeck.spectrum import SpectrumController, capture_command, goertzel, log_frequencies, release_level, spectrum_power_level, stereo_vu_levels


class SpectrumMathTests(unittest.TestCase):
    def test_bar_release_is_slow_but_attack_is_immediate(self):
        self.assertEqual(release_level(0.2, 0.9, 0.1, 0.8), 0.9)
        self.assertAlmostEqual(release_level(1.0, 0.0, 0.2, 0.8), 0.75)
        self.assertEqual(release_level(0.2, 0.3, 0.2, 0.8), 0.3)
        self.assertEqual(release_level(1.0, 0.0, 0.1, 0), 0.0)
        level = 1.0
        for _ in range(8):
            level = release_level(level, 0.0, 0.1, 0.8)
        self.assertAlmostEqual(level, 0.0)
        self.assertAlmostEqual(release_level(1.0, 0.0, 0.8, 0.8), level)

    def test_visual_gain_is_a_fixed_db_offset_and_silence_stays_zero(self):
        n = 1024
        for db in (-45, -30):
            amplitude = 32768 * 10 ** (db / 20)
            power = (amplitude * n / 4) ** 2
            base = spectrum_power_level(power, n)
            boosted = spectrum_power_level(power, n, gain_db=12)
            self.assertAlmostEqual(boosted - base, 12 / 60)
        self.assertEqual(spectrum_power_level(0, n, gain_db=30), 0)

    def test_fixed_spectrum_scale_tracks_dbfs_without_auto_gain(self) -> None:
        sample_rate = 16_000
        sample_count = 1024
        frequency = 1000.0
        coefficient = 2.0 * math.cos(2.0 * math.pi * frequency / sample_rate)
        loud = tuple(round(32767 * math.sin(2.0 * math.pi * frequency * index / sample_rate)) for index in range(sample_count))
        quiet = tuple(round(33 * math.sin(2.0 * math.pi * frequency * index / sample_rate)) for index in range(sample_count))
        self.assertGreater(spectrum_power_level(goertzel(loud, coefficient), sample_count), 0.98)
        self.assertLess(spectrum_power_level(goertzel(quiet, coefficient), sample_count), 0.05)

    def test_stereo_vu_keeps_left_and_right_channels_independent(self) -> None:
        samples = tuple(value for _ in range(200) for value in (20_000, 500))
        left, right = stereo_vu_levels(samples)
        self.assertGreater(left, right)
        self.assertGreater(left, 0.8)
        self.assertLess(right, 0.4)

    def test_stereo_capture_requests_two_channels(self) -> None:
        self.assertIn("--channels=2", capture_command("parec", "test", 16_000, channels=2))

    def test_capture_requests_low_latency(self) -> None:
        command = capture_command("/usr/bin/parec", "test.monitor", 16_000)
        self.assertIn("--latency-msec=40", command)
        self.assertIn("--process-time-msec=40", command)
        self.assertIn("--device=test.monitor", command)

    def test_log_frequencies_cover_requested_range(self) -> None:
        values = log_frequencies(8, 55.0, 7000.0)
        self.assertEqual(len(values), 8)
        self.assertAlmostEqual(values[0], 55.0)
        self.assertAlmostEqual(values[-1], 7000.0)
        self.assertTrue(all(left < right for left, right in zip(values, values[1:])))

    def test_goertzel_detects_matching_tone(self) -> None:
        rate = SpectrumController.SAMPLE_RATE
        samples = tuple(int(12000 * math.sin(2 * math.pi * 1000 * index / rate)) for index in range(1024))
        matching = goertzel(samples, 2 * math.cos(2 * math.pi * 1000 / rate))
        distant = goertzel(samples, 2 * math.cos(2 * math.pi * 3000 / rate))
        self.assertGreater(matching, distant * 100)


if __name__ == "__main__":
    unittest.main()
