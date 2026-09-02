import json
import tempfile
import unittest
from pathlib import Path

from sdeck.model import ACTION_KEYBOARD, ACTION_MULTI, ACTION_SHELL, ACTION_SPECTRUM, ACTION_VU, AppConfig, KeyConfig, MultiActionStep, default_visualizer_icon, replicate_key_config


class ConfigTests(unittest.TestCase):
    def test_visualizer_fallback_icons_only_apply_without_preview(self) -> None:
        spectrum = KeyConfig(action=ACTION_SPECTRUM, spectrum_preview=False)
        vu = KeyConfig(action=ACTION_VU, vu_preview=False)
        self.assertTrue(default_visualizer_icon(spectrum).endswith("audio-waveform.svg"))
        self.assertTrue(default_visualizer_icon(vu).endswith("sliders-horizontal.svg"))
        spectrum.spectrum_preview = True
        vu.vu_preview = True
        self.assertEqual(default_visualizer_icon(spectrum), "")
        self.assertEqual(default_visualizer_icon(vu), "")

    def test_key_configuration_replication_is_deep_and_resets_runtime_state(self) -> None:
        nested = KeyConfig(label="Nested", action=ACTION_KEYBOARD, keyboard_shortcut="F22")
        source = KeyConfig(label="Source", action=ACTION_MULTI, active=True, started_at="2026-01-01T00:00:00+00:00")
        source.multi_action_in = [MultiActionStep(action=nested.to_dict())]
        destination = KeyConfig(label="Old")
        replicate_key_config(source, destination)
        self.assertEqual((destination.label, destination.action), ("Source", ACTION_MULTI))
        self.assertFalse(destination.active)
        self.assertIsNone(destination.started_at)
        destination.multi_action_in[0].action["label"] = "Changed"
        self.assertEqual(source.multi_action_in[0].action["label"], "Nested")

    def test_default_config_has_one_complete_space(self) -> None:
        config = AppConfig.default()
        self.assertEqual(config.current().name, "Main")
        self.assertEqual(len(config.current().keys), 15)
        self.assertEqual(config.current_space, config.current().id)

    def test_round_trip_preserves_actions_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig.default()
            config.language = "es"
            key = config.current().keys[3]
            key.label = "Transmitir"
            key.action = ACTION_SHELL
            key.command = "echo start"
            key.toggle = True
            key.active = True
            key.started_at = "2026-08-30T20:00:00+00:00"
            second = config.add_space("Audio")
            config.current_space = second.id
            config.save(path)
            restored = AppConfig.load(path)
            self.assertEqual(restored.current().name, "Audio")
            self.assertEqual(restored.spaces[0].keys[3].label, "Transmitir")
            self.assertTrue(restored.spaces[0].keys[3].active)
            self.assertEqual(restored.language, "es")

    def test_round_trip_preserves_glyph_and_spectrum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig.default()
            key = config.current().keys[0]
            key.glyph = "●"
            key.active_glyph = "■"
            key.action = "spectrum"
            key.spectrum_operation = "start"
            key.spectrum_target = "output.test"
            key.spectrum_fps = 12
            key.spectrum_preview = True
            key.spectrum_grid_size = 3
            config.save(path)
            restored = AppConfig.load(path).current().keys[0]
            self.assertEqual((restored.glyph, restored.active_glyph), ("●", "■"))
            self.assertEqual((restored.spectrum_target, restored.spectrum_fps), ("output.test", 12))
            self.assertTrue(restored.spectrum_preview)
            self.assertEqual(restored.spectrum_grid_size, 3)

    def test_round_trip_preserves_stereo_vu_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig.default()
            key = config.current().keys[0]
            key.action = "vu"
            key.vu_target = "output.test"
            key.vu_fps = 14
            key.vu_preview = True
            key.vu_color_start = "#00ff80"
            key.vu_color_end = "#ff0080"
            config.save(path)
            restored = AppConfig.load(path).current().keys[0]
            self.assertEqual(restored.action, "vu")
            self.assertEqual((restored.vu_target, restored.vu_fps), ("output.test", 14))
            self.assertTrue(restored.vu_preview)
            self.assertEqual((restored.vu_color_start, restored.vu_color_end), ("#00ff80", "#ff0080"))

    def test_round_trip_preserves_key_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig.default()
            key = config.current().keys[0]
            key.background_color = "#123456"
            key.active_background_color = "#654321"
            key.text_color = "#abcdef"
            key.icon_color = "#fedcba"
            config.save(path)
            restored = AppConfig.load(path).current().keys[0]
            self.assertEqual(
                (restored.background_color, restored.active_background_color, restored.text_color, restored.icon_color),
                ("#123456", "#654321", "#abcdef", "#fedcba"),
            )

    def test_round_trip_preserves_keyboard_and_multi_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig.default()
            key = config.current().keys[0]
            key.action = ACTION_MULTI
            key.toggle = True
            nested = KeyConfig(action=ACTION_KEYBOARD, keyboard_shortcut="CTRL+F22")
            key.multi_action_in = [MultiActionStep("action", 0, True, nested.to_dict()), MultiActionStep("pause", 750)]
            key.multi_action_out = [MultiActionStep("action", 0, False, nested.to_dict())]
            config.save(path)
            restored = AppConfig.load(path).current().keys[0]
            self.assertEqual(restored.action, ACTION_MULTI)
            self.assertEqual(restored.multi_action_in[0].action["keyboard_shortcut"], "CTRL+F22")
            self.assertEqual(restored.multi_action_in[1].delay_ms, 750)
            self.assertFalse(restored.multi_action_out[0].desired_state)

    def test_obs_connection_is_global_and_migrates_legacy_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "key_count": 1,
                        "columns": 1,
                        "spaces": [
                            {
                                "id": "main",
                                "name": "Principal",
                                "keys": [
                                    {
                                        "action": "obs",
                                        "obs_url": "ws://obs.local:4455",
                                        "obs_password": "secret",
                                        "obs_operation": "scene",
                                        "obs_target": "Cámara",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            config = AppConfig.load(path)
            self.assertEqual(config.obs_url, "ws://obs.local:4455")
            self.assertEqual(config.obs_password, "secret")
            self.assertNotIn("obs_url", config.current().keys[0].to_dict())
            config.save(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["obs_url"], "ws://obs.local:4455")
            self.assertNotIn("obs_url", saved["spaces"][0]["keys"][0])

    def test_load_repairs_missing_keys_and_invalid_current_space(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"key_count": 4, "columns": 2, "current_space": "missing", "spaces": [{"id": "one", "name": "One", "keys": [{}]}]}), encoding="utf-8")
            config = AppConfig.load(path)
            self.assertEqual(config.current_space, "one")
            self.assertEqual(len(config.current().keys), 4)

    def test_duplicate_has_independent_keys(self) -> None:
        config = AppConfig.default()
        original = config.current()
        copy = config.duplicate_space(original, "Copia")
        copy.keys[0].label = "Otro"
        self.assertEqual(original.keys[0].label, "")

    def test_corrupt_file_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{not-json", encoding="utf-8")
            self.assertEqual(AppConfig.load(path).current().name, "Main")

    def test_switching_to_smaller_layout_preserves_hidden_keys(self) -> None:
        config = AppConfig.default()
        config.apply_layout("xl", 32, 8)
        config.current().keys[20].label = "No perder"
        config.apply_layout("mini", 6, 3)
        config.apply_layout("xl", 32, 8)
        self.assertEqual(config.current().keys[20].label, "No perder")


if __name__ == "__main__":
    unittest.main()
