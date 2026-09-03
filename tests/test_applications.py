import tempfile
import unittest
from pathlib import Path

from sdeck.applications import desktop_activation_uri, desktop_exec, read_desktop_application
from sdeck.i18n import set_language, tr


class DesktopApplicationTests(unittest.TestCase):
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

    def test_discord_handler_uses_uri_that_activates_existing_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discord.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Discord\nExec=discord %U\n"
                "MimeType=x-scheme-handler/discord;\n",
                encoding="utf-8",
            )
            self.assertEqual(desktop_activation_uri(path), "discord://-/channels/@me")

    def test_unknown_uri_handler_keeps_standard_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.desktop"
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Example\nExec=example %U\n"
                "MimeType=x-scheme-handler/example;\n",
                encoding="utf-8",
            )
            self.assertEqual(desktop_activation_uri(path), "")

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
