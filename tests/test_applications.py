import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sdeck.applications import desktop_exec, desktop_launch_command, read_desktop_application
from sdeck.i18n import set_language, tr


class DesktopApplicationTests(unittest.TestCase):
    def test_flatpak_export_path_produces_registered_desktop_id(self) -> None:
        from sdeck.applications import desktop_file_id

        path = Path("/var/lib/flatpak/exports/share/applications/com.example.App.desktop")
        self.assertEqual(desktop_file_id(path), "com.example.App.desktop")

    def test_reads_standard_desktop_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Example App\nComment=Demo\nIcon=example\nExec=example --open\n",
                encoding="utf-8",
            )
            application = read_desktop_application(path)
            self.assertIsNotNone(application)
            self.assertEqual(application.name, "Example App")
            self.assertEqual(application.icon_name, "example")

    def test_exec_removes_file_placeholders_and_expands_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Example App\nIcon=example\nExec=/usr/bin/example --name %c %U %% %k\n",
                encoding="utf-8",
            )
            program, arguments = desktop_exec(path)
            self.assertEqual(program, "/usr/bin/example")
            self.assertEqual(arguments, ["--name", "Example App", "%", str(path)])

    @patch("sdeck.applications.desktop_file_id", return_value="com.example.App.desktop")
    @patch("sdeck.applications.QStandardPaths.findExecutable")
    def test_kde_uses_its_native_application_launcher(self, find_executable, _desktop_id) -> None:
        find_executable.side_effect = lambda name: "/usr/bin/kstart5" if name == "kstart5" else ""
        self.assertEqual(
            desktop_launch_command(Path("/apps/com.example.App.desktop"), "KDE"),
            ("/usr/bin/kstart5", ["--application", "com.example.App"]),
        )

    @patch("sdeck.applications.desktop_file_id", return_value="com.example.App.desktop")
    @patch("sdeck.applications.QStandardPaths.findExecutable")
    def test_gnome_uses_gtk_launcher(self, find_executable, _desktop_id) -> None:
        find_executable.side_effect = lambda name: "/usr/bin/gtk-launch" if name == "gtk-launch" else ""
        self.assertEqual(
            desktop_launch_command(Path("/apps/com.example.App.desktop"), "GNOME"),
            ("/usr/bin/gtk-launch", ["com.example.App"]),
        )

    @patch("sdeck.applications.desktop_file_id", return_value="")
    @patch("sdeck.applications.QStandardPaths.findExecutable", return_value="/usr/bin/gio")
    def test_unregistered_shortcut_uses_gio_fallback(self, _find_executable, _desktop_id) -> None:
        path = Path("/home/test/Desktop/example.desktop")
        self.assertEqual(desktop_launch_command(path, "KDE"), ("/usr/bin/gio", ["launch", str(path)]))

    def test_spanish_catalog_translates_english_base_text(self) -> None:
        set_language("es")
        self.assertEqual(tr("Open application"), "Abrir aplicación")
        set_language("en")
        self.assertEqual(tr("Open application"), "Open application")

    def test_application_name_follows_selected_interface_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Settings\nName[es]=Ajustes\nExec=settings\n",
                encoding="utf-8",
            )
            set_language("es")
            self.assertEqual(read_desktop_application(path).name, "Ajustes")
            set_language("en")
            self.assertEqual(read_desktop_application(path).name, "Settings")


if __name__ == "__main__":
    unittest.main()
