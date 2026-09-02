import math
import unittest

from sdeck.spectrum import SpectrumController, capture_command, goertzel, log_frequencies, stereo_vu_levels


class SpectrumMathTests(unittest.TestCase):
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
