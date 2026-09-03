import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
INSTALLER = PROJECT_DIR / "packaging" / "install-appimage-user.sh"
DESKTOP_TEMPLATE = PROJECT_DIR / "packaging" / "sdeck.appimage.desktop"
ICON = PROJECT_DIR / "assets" / "sdeck.svg"


class AppImageUserInstallerTests(unittest.TestCase):
    def test_install_autostart_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_home = root / "data"
            config_home = root / "config"
            source = root / "Downloaded YASDEC.AppImage"
            source.write_bytes(b"fake-appimage")
            source.chmod(0o755)
            environment = os.environ.copy()
            environment["XDG_DATA_HOME"] = str(data_home)
            environment["XDG_CONFIG_HOME"] = str(config_home)

            subprocess.run(
                ["bash", str(INSTALLER), "install", str(source), str(DESKTOP_TEMPLATE), str(ICON), "--autostart"],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )

            installed = data_home / "yasdec" / "YASDEC-x86_64.AppImage"
            desktop = data_home / "applications" / "sdeck.desktop"
            autostart = config_home / "autostart" / "sdeck.desktop"
            self.assertEqual(installed.read_bytes(), b"fake-appimage")
            self.assertTrue(installed.stat().st_mode & stat.S_IXUSR)
            self.assertIn(f'Exec="{installed}"', desktop.read_text())
            self.assertIn(f'Exec="{installed}" --background', autostart.read_text())

            personal_config = config_home / "SDeck" / "config.json"
            personal_config.parent.mkdir(parents=True)
            personal_config.write_text("{}")
            subprocess.run(
                ["bash", str(INSTALLER), "uninstall", str(source), str(DESKTOP_TEMPLATE), str(ICON)],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertFalse(installed.exists())
            self.assertFalse(desktop.exists())
            self.assertFalse(autostart.exists())
            self.assertTrue(personal_config.exists())


if __name__ == "__main__":
    unittest.main()
