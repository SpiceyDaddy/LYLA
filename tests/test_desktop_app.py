import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import desktop_app


class DesktopAppTests(unittest.TestCase):
    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "desktop.json"
            with patch.object(desktop_app, "APP_SETTINGS_PATH", settings_path):
                desktop_app.save_settings(
                    {
                        "voicebox_profile": "LYLA",
                        "voicebox_app": r"C:\Apps\Voicebox.exe",
                    }
                )
                self.assertEqual(
                    desktop_app.load_settings(),
                    {
                        "voicebox_profile": "LYLA",
                        "voicebox_app": r"C:\Apps\Voicebox.exe",
                    },
                )
                self.assertEqual(
                    json.loads(settings_path.read_text(encoding="utf-8"))[
                        "voicebox_profile"
                    ],
                    "LYLA",
                )

    def test_missing_settings_use_voicebox_default_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                desktop_app,
                "APP_SETTINGS_PATH",
                Path(directory) / "missing.json",
            ):
                self.assertEqual(
                    desktop_app.load_settings(),
                    {"voicebox_profile": "", "voicebox_app": ""},
                )


if __name__ == "__main__":
    unittest.main()
