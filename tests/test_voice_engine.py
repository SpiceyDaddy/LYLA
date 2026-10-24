import unittest
from unittest.mock import patch

from src.lyla_voice import handle_response
from src.voice_engine import VoiceStartupError, speak


class VoiceEngineTests(unittest.TestCase):
    def test_voice_initialization_failure_is_clear(self):
        with patch("pyttsx3.init", side_effect=OSError("no speech engine")):
            with self.assertRaises(VoiceStartupError) as error:
                speak("Hello")
        self.assertIn("Windows text-to-speech", str(error.exception))

    def test_missing_voice_dependency_has_install_instructions(self):
        original_import = __import__

        def fail_voice_import(name, *args, **kwargs):
            if name == "pyttsx3":
                raise ModuleNotFoundError("pyttsx3 is missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_voice_import):
            with self.assertRaises(VoiceStartupError) as error:
                speak("Hello")
        self.assertIn("pip install -r requirements.txt", str(error.exception))

    def test_text_response_survives_unavailable_voice(self):
        with patch(
            "src.lyla_voice.speak",
            side_effect=VoiceStartupError("speech engine unavailable"),
        ):
            with patch("builtins.print") as print_output:
                handle_response("Text still works.", "neutral")

        printed = "\n".join(str(call.args[0]) for call in print_output.call_args_list)
        self.assertIn("LYLA: Text still works.", printed)
        self.assertIn("[Voice unavailable]", printed)


if __name__ == "__main__":
    unittest.main()
