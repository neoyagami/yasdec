import tomllib
import unittest
from pathlib import Path

from sdeck import __version__


class VersionTests(unittest.TestCase):
    def test_package_metadata_matches_runtime_version(self) -> None:
        project = Path(__file__).resolve().parent.parent
        metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)


if __name__ == "__main__":
    unittest.main()
