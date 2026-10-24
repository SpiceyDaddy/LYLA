import unittest

from src.state_engine import get_state


class StateEngineTests(unittest.TestCase):
    def test_keyword_routing_is_case_insensitive(self):
        self.assertEqual(get_state("HELLO there"), "Engage")
        self.assertEqual(get_state("I am TIRED"), "Support")
        self.assertEqual(get_state("Show STATUS"), "Report")

    def test_keyword_routing_uses_word_boundaries(self):
        self.assertEqual(get_state("I like the word exiting"), "LLM")
        self.assertEqual(get_state("I feel happy today"), "Celebrate")
        self.assertEqual(get_state("goodbye"), "Farewell")


if __name__ == "__main__":
    unittest.main()
