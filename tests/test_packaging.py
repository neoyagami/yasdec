import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
INSTALLER = PROJECT_DIR / "packaging" / "install-appimage-user.sh"
APP_RUN = PROJECT_DIR / "packaging" / "AppRun"
DESKTOP_TEMPLATE = PROJECT_DIR / "packaging" / "sdeck.appimage.desktop"
ICON = PROJECT_DIR / "assets" / "sdeck.svg"


class AppImageUserInstallerTests(unittest.TestCase):
    def test_apprun_help_lists_management_and_runtime_options(self) -> None:
        result = subprocess.run(
            ["bash", str(APP_RUN), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        for option in (
            "--background",
            "--install-user",
            "--autostart",
            "--uninstall-user",
            "--install-uinput",
            "--remove-uinput",
        ):
            self.assertIn(option, result.stdout)
        self.assertIn("do not run the AppImage with sudo", result.stdout)

    def test_apprun_accepts_combined_install_flags_in_any_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_dir = root / "AppDir"
            support = app_dir / "usr" / "share" / "sdeck"
            support.mkdir(parents=True)
            shutil.copy2(INSTALLER, support / "install-appimage-user.sh")
            for name in ("install-uinput.sh", "70-sdeck-uinput.rules", "sdeck-uinput.conf"):
                shutil.copy2(PROJECT_DIR / "packaging" / name, support / name)
            shutil.copy2(DESKTOP_TEMPLATE, app_dir / "sdeck.desktop")
            shutil.copy2(ICON, app_dir / "sdeck.svg")
            source = root / "YASDEC-x86_64.AppImage"
            source.write_bytes(b"fake-appimage")
            source.chmod(0o755)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "pkexec").symlink_to("/usr/bin/true")
            environment = os.environ.copy()
            environment.update({
                "APPDIR": str(app_dir),
                "APPIMAGE": str(source),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "PATH": f"{fake_bin}:{environment.get('PATH', '/usr/bin:/bin')}",
            })

            subprocess.run(
                ["bash", str(APP_RUN), "--install-uinput", "--install-user", "--autostart"],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertTrue((root / "data" / "yasdec" / "YASDEC-x86_64.AppImage").is_file())
            self.assertTrue((root / "data" / "applications" / "sdeck.desktop").is_file())
            self.assertTrue((root / "config" / "autostart" / "sdeck.desktop").is_file())

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
