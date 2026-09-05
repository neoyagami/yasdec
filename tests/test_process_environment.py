import unittest
from unittest.mock import patch

from sdeck.process_environment import external_process_environment


class ExternalProcessEnvironmentTests(unittest.TestCase):
    def test_appimage_launch_uses_host_qt_plugins_and_keeps_desktop_connection(self) -> None:
        source = {
            "APPDIR": "/tmp/.mount_YASDEC",
            "QT_PLUGIN_PATH": "/tmp/.mount_YASDEC/usr/lib/PySide6/Qt/plugins",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/.mount_YASDEC/usr/lib/PySide6/Qt/plugins/platforms",
            "LD_LIBRARY_PATH": "/tmp/.mount_YASDEC/usr/lib",
            "WAYLAND_DISPLAY": "wayland-0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "QT_QPA_PLATFORM": "wayland",
        }
        environment = external_process_environment(source)
        for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "LD_LIBRARY_PATH"):
            self.assertNotIn(name, environment)
            self.assertIn(name, source)
        for name in ("WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "QT_QPA_PLATFORM"):
            self.assertEqual(environment[name], source[name])

    @patch("sdeck.process_environment.sys.frozen", True, create=True)
    def test_frozen_launch_without_appimage_also_removes_bundled_qt_plugins(self) -> None:
        self.assertEqual(external_process_environment({"QT_PLUGIN_PATH": "/bundle/plugins"}), {})

    @patch("sdeck.process_environment.sys.frozen", False, create=True)
    def test_source_launch_preserves_host_qt_plugin_settings(self) -> None:
        source = {"QT_PLUGIN_PATH": "/opt/qt/plugins"}
        self.assertEqual(external_process_environment(source), source)

    def test_restores_original_library_path_for_frozen_application(self) -> None:
        environment = external_process_environment({
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/appimage/usr/lib",
            "LD_LIBRARY_PATH_ORIG": "/opt/host/lib",
        })
        self.assertEqual(environment["LD_LIBRARY_PATH"], "/opt/host/lib")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", environment)

    def test_removes_bundled_library_path_when_no_original_existed(self) -> None:
        environment = external_process_environment({
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/appimage/usr/lib",
        })
        self.assertEqual(environment, {"PATH": "/usr/bin"})

    def test_removes_stale_single_use_activation_identifiers(self) -> None:
        environment = external_process_environment({
            "PATH": "/usr/bin",
            "XDG_ACTIVATION_TOKEN": "already-consumed-wayland-token",
            "DESKTOP_STARTUP_ID": "already-consumed-x11-token",
        })
        self.assertEqual(environment, {"PATH": "/usr/bin"})


if __name__ == "__main__":
    unittest.main()
