import unittest

from src.evaluate_conversations import CASES, score_response


class EvaluationTests(unittest.TestCase):
    def test_cases_cover_requested_conversation_skills(self):
        self.assertGreaterEqual(len(CASES), 4)
        names = {case["name"] for case in CASES}
        self.assertIn("factual question", names)
        self.assertIn("follow a format instruction", names)
        self.assertIn("use short-term context", names)
        self.assertIn("stay in LYLA's persona", names)

    def test_score_checks_answer_instruction_and_prompt_echo(self):
        case = {
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
            "expected_terms": ["Paris"],
            "max_words": 10,
        }
        good = score_response(case, "Paris is the capital of France.")
        self.assertTrue(good["answers_question"])
        self.assertTrue(good["follows_instructions"])
        self.assertTrue(good["does_not_repeat_prompt"])

        echoed = score_response(case, "What is the capital of France?")
        self.assertFalse(echoed["does_not_repeat_prompt"])


if __name__ == "__main__":
    unittest.main()
