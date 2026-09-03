import unittest

from sdeck.process_environment import external_process_environment


class ExternalProcessEnvironmentTests(unittest.TestCase):
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
