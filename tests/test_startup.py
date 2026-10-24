import unittest
from unittest.mock import patch

from src import lyla
from src.lyla_core.text_pipeline import ModelStartupError


class StartupTests(unittest.TestCase):
    def test_model_error_is_reported_and_cli_remains_available(self):
        with patch("builtins.input", side_effect=["What is the weather?", "goodbye"]):
            with patch("src.lyla.ConversationManager") as manager_class:
                manager_class.return_value.ask.side_effect = ModelStartupError(
                    "local model could not load"
                )
                with patch("src.lyla.handle_response") as handle_response:
                    lyla.main()

        self.assertTrue(
            any(
                "local model could not load" in str(call.args[0])
                for call in handle_response.call_args_list
            )
        )
        self.assertEqual(manager_class.return_value.ask.call_count, 1)


if __name__ == "__main__":
    unittest.main()
