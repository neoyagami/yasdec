import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from sdeck.actions import ActionRunner
from sdeck.model import ACTION_KEYBOARD, ACTION_SPECTRUM, ACTION_VU, KeyConfig
from sdeck.window import MainWindow


app = QCoreApplication.instance() or QCoreApplication([])


class VisualizerInputTests(unittest.TestCase):
    def test_any_key_dismisses_visualizer_without_executing_its_action(self):
        for action in (ACTION_SPECTRUM, ACTION_VU):
            for preview in (False, True):
                for pressed in range(4):
                    with self.subTest(action=action, preview=preview, pressed=pressed):
                        runner = ActionRunner()
                        try:
                            runner.audio.timer.stop()
                            runner._timer.stop()
                            runner.audio.capture_device = lambda *_args: "monitor.test"
                            runner.spectrum.start = Mock(return_value=True)
                            runner.spectrum.stop = Mock()
                            runner.vu.start = Mock(return_value=True)
                            runner.vu.stop = Mock()
                            runner.keyboard.send = Mock()
                            visual = KeyConfig(action=action, spectrum_preview=preview,
                                               vu_preview=preview, toggle=True)
                            shortcut = KeyConfig(action=ACTION_KEYBOARD, keyboard_shortcut="F22")
                            other = KeyConfig(action=ACTION_VU if action == ACTION_SPECTRUM else ACTION_SPECTRUM)
                            keys = [visual, shortcut, KeyConfig(), other]
                            runner._visible_keys = keys
                            window = SimpleNamespace(
                                runner=runner, schedule_save=Mock(),
                                config=SimpleNamespace(current=lambda: SimpleNamespace(keys=keys),
                                                       current_space="main"),
                            )
                            MainWindow.trigger_key(window, 0)
                            self.assertTrue(runner.spectrum_fullscreen or runner.vu_fullscreen)
                            MainWindow.trigger_key(window, pressed)
                            self.assertFalse(runner.spectrum_fullscreen)
                            self.assertFalse(runner.vu_fullscreen)
                            self.assertFalse(visual.active)
                            self.assertEqual(runner.spectrum_active if action == ACTION_SPECTRUM
                                             else runner.vu_active, preview)
                            runner.keyboard.send.assert_not_called()
                            (runner.vu.start if action == ACTION_SPECTRUM
                             else runner.spectrum.start).assert_not_called()
                            # Once the grid is visible again, a new press runs normally.
                            MainWindow.trigger_key(window, 1)
                            runner.keyboard.send.assert_called_once_with("F22")
                        finally:
                            runner.close()
