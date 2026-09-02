import unittest
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt

from sdeck.actions import ActionRunner, elapsed_text
from sdeck.keyboard import ShortcutError, shortcut_from_qt, shortcut_names
from sdeck.model import ACTION_KEYBOARD, ACTION_MULTI, ACTION_SPECTRUM, ACTION_VU, KeyConfig, MultiActionStep


app = QCoreApplication.instance() or QCoreApplication([])


class ElapsedTextTests(unittest.TestCase):
    def test_active_timer(self) -> None:
        key = KeyConfig(active=True, started_at=(datetime.now(timezone.utc) - timedelta(seconds=65)).isoformat())
        self.assertIn(elapsed_text(key), {"01:04", "01:05", "01:06"})

    def test_inactive_timer(self) -> None:
        key = KeyConfig(active=False, started_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(elapsed_text(key), "")


class SpectrumToggleTests(unittest.TestCase):
    def test_lcd_grid_uses_the_full_horizontal_resolution_and_updates_live(self) -> None:
        runner = ActionRunner()
        runner.audio.timer.stop()
        runner._timer.stop()
        runner.audio.capture_device = lambda *_args: "monitor.test"
        starts: list[int] = []
        runner.spectrum.start = lambda _device, bands: starts.append(bands) or True
        runner.spectrum.stop = lambda: None
        key = KeyConfig(
            action=ACTION_SPECTRUM,
            spectrum_operation="start",
            spectrum_target="test",
            spectrum_grid_size=1,
        )
        runner._visible_keys = [key]
        runner._spectrum_columns = 5

        runner.trigger(0, key)
        self.assertEqual(starts, [5])
        key.spectrum_grid_size = 3
        runner.sync_spectrum_preview()
        self.assertEqual(starts, [5, 15])
        self.assertEqual(runner._spectrum_band_count, 15)
        runner.close()

    def test_preview_keeps_capture_after_fullscreen_is_toggled_off(self) -> None:
        runner = ActionRunner()
        runner.audio.timer.stop()
        runner._timer.stop()
        runner.audio.capture_device = lambda *_args: "monitor.test"
        runner.spectrum.start = lambda *_args: True
        runner.spectrum.stop = lambda: None
        key = KeyConfig(
            action=ACTION_SPECTRUM,
            spectrum_operation="start",
            spectrum_target="test",
            spectrum_preview=True,
            toggle=True,
        )
        runner._visible_keys = [key]
        runner._spectrum_columns = 5

        runner.trigger(0, key)
        self.assertTrue(runner.spectrum_fullscreen)
        self.assertTrue(key.active)

        runner.trigger(0, key)
        self.assertTrue(runner.spectrum_active)
        self.assertFalse(runner.spectrum_fullscreen)
        self.assertFalse(key.active)

        key.spectrum_preview = False
        runner.sync_spectrum_preview()
        self.assertFalse(runner.spectrum_active)
        runner.close()


class StereoVuToggleTests(unittest.TestCase):
    def test_preview_keeps_stereo_capture_after_fullscreen_toggle(self) -> None:
        runner = ActionRunner()
        runner.audio.timer.stop()
        runner._timer.stop()
        runner.audio.capture_device = lambda *_args: "monitor.test"
        starts: list[str] = []
        runner.vu.start = lambda device: starts.append(device) or True
        runner.vu.stop = lambda: None
        key = KeyConfig(action=ACTION_VU, vu_target="test", vu_preview=True, toggle=True)
        runner._visible_keys = [key]

        runner.trigger(0, key)
        self.assertTrue(runner.vu_fullscreen)
        self.assertTrue(key.active)
        self.assertEqual(starts, ["monitor.test"])

        runner.trigger(0, key)
        self.assertTrue(runner.vu_active)
        self.assertFalse(runner.vu_fullscreen)
        self.assertFalse(key.active)
        runner.close()

    def test_spectrum_and_vu_previews_run_together_but_fullscreen_is_exclusive(self) -> None:
        runner = ActionRunner()
        runner.audio.timer.stop()
        runner._timer.stop()
        runner.audio.capture_device = lambda *_args: "monitor.test"
        runner.spectrum.start = lambda *_args: True
        runner.spectrum.stop = lambda: None
        runner.vu.start = lambda *_args: True
        runner.vu.stop = lambda: None
        spectrum = KeyConfig(action=ACTION_SPECTRUM, spectrum_preview=True, toggle=True)
        vu = KeyConfig(action=ACTION_VU, vu_preview=True, toggle=True)
        runner._visible_keys = [spectrum, vu]

        runner._sync_visual_previews()
        self.assertTrue(runner.spectrum_active)
        self.assertTrue(runner.vu_active)
        self.assertFalse(runner.spectrum_fullscreen)
        self.assertFalse(runner.vu_fullscreen)

        runner.trigger(0, spectrum)
        self.assertTrue(runner.spectrum_fullscreen)
        self.assertFalse(runner.vu_active)

        runner.trigger(0, spectrum)
        self.assertFalse(runner.spectrum_fullscreen)
        self.assertTrue(runner.spectrum_active)
        self.assertTrue(runner.vu_active)
        runner.close()

class KeyboardShortcutTests(unittest.TestCase):
    def test_qt_recorder_formats_modifiers_and_extended_function_keys(self) -> None:
        modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        self.assertEqual(shortcut_from_qt(Qt.Key.Key_F22, modifiers), "Ctrl+Alt+F22")
        self.assertEqual(shortcut_names(shortcut_from_qt(Qt.Key.Key_F22, modifiers)), ["KEY_LEFTCTRL", "KEY_LEFTALT", "KEY_F22"])

    def test_shortcut_parser_supports_f22_and_modifiers(self) -> None:
        self.assertEqual(shortcut_names("ctrl + shift + F22"), ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_F22"])

    def test_shortcut_parser_rejects_empty_components(self) -> None:
        with self.assertRaises(ShortcutError):
            shortcut_names("CTRL++F22")


class MultiActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = ActionRunner()
        self.runner.audio.timer.stop()
        self.runner._timer.stop()
        self.sent: list[str] = []
        self.runner.keyboard.send = self.sent.append

    def tearDown(self) -> None:
        self.runner.close()

    @staticmethod
    def keyboard_step(shortcut: str, desired: bool = True) -> MultiActionStep:
        action = KeyConfig(action=ACTION_KEYBOARD, keyboard_shortcut=shortcut)
        return MultiActionStep("action", 0, desired, action.to_dict())

    def test_in_and_out_lists_toggle_the_parent(self) -> None:
        key = KeyConfig(
            action=ACTION_MULTI,
            toggle=True,
            multi_action_in=[self.keyboard_step("F22")],
            multi_action_out=[self.keyboard_step("F23", False)],
        )
        self.runner.trigger(0, key)
        self.assertEqual(self.sent, ["F22"])
        self.assertTrue(key.active)
        self.runner.trigger(0, key)
        self.assertEqual(self.sent, ["F22", "F23"])
        self.assertFalse(key.active)

    def test_pause_preserves_step_order(self) -> None:
        key = KeyConfig(
            action=ACTION_MULTI,
            toggle=True,
            multi_action_in=[
                self.keyboard_step("F20"),
                MultiActionStep("pause", 5),
                self.keyboard_step("F21"),
            ],
        )
        self.runner.trigger(0, key)
        self.assertEqual(self.sent, ["F20"])
        self.assertFalse(key.active)
        loop = QEventLoop()
        QTimer.singleShot(30, loop.quit)
        loop.exec()
        self.assertEqual(self.sent, ["F20", "F21"])
        self.assertTrue(key.active)


if __name__ == "__main__":
    unittest.main()
