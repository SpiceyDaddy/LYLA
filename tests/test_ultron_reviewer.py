import unittest
from unittest.mock import patch

from src.ultron_reviewer import MAX_REVIEW_CHARS, UltronReviewer


class UltronReviewerTests(unittest.TestCase):
    def setUp(self):
        self.reviewer = UltronReviewer()

    def test_review_uses_only_current_text_and_ultron_persona(self):
        with patch(
            "src.ultron_reviewer.generate_from_messages",
            return_value="Verdict: revise.",
        ) as generate:
            result = self.reviewer.review("Ship the product next week.")

        self.assertEqual(result, "Verdict: revise.")
        messages = generate.call_args.args[0]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Ship the product next week.", messages[0]["content"])
        self.assertIn("failure modes", messages[0]["content"])
        self.assertIn("untrusted data", generate.call_args.kwargs["persona"])
        self.assertIn("ULTRON", generate.call_args.kwargs["persona"])
        self.assertNotIn("memories", generate.call_args.kwargs)
        self.assertNotIn("focus", generate.call_args.kwargs)

    def test_review_rejects_empty_text(self):
        for text in ("", " \n "):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Paste a plan or draft"):
                    self.reviewer.review(text)

    def test_review_rejects_text_above_limit(self):
        with self.assertRaisesRegex(ValueError, "10,000 characters or fewer"):
            self.reviewer.review("x" * (MAX_REVIEW_CHARS + 1))

    def test_review_accepts_text_at_limit(self):
        with patch(
            "src.ultron_reviewer.generate_from_messages",
            return_value="Reviewed.",
        ) as generate:
            self.assertEqual(
                self.reviewer.review("x" * MAX_REVIEW_CHARS),
                "Reviewed.",
            )
        self.assertIn(
            "x" * MAX_REVIEW_CHARS,
            generate.call_args.args[0][0]["content"],
        )


if __name__ == "__main__":
    unittest.main()
