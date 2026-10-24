import unittest
from unittest.mock import patch

from src.agents import get_agent
from src.conversation_manager import ConversationManager
from src.memory import MindMemory, SoulMemory


class ConversationManagerTests(unittest.TestCase):
    def test_sends_mind_soul_and_focus_to_the_model_and_commits_turn(self):
        soul = SoulMemory()
        soul.persona = "Be kind."
        soul.memories = ["The user likes gardening."]
        mind = MindMemory()
        mind.focus = "plan a garden"
        manager = ConversationManager(soul=soul, mind=mind)

        with patch(
            "src.conversation_manager.generate_from_messages",
            return_value="Let's start with herbs.",
        ) as generate:
            reply, _ = manager.ask("What should I plant?")

        generate.assert_called_once_with(
            [{"role": "user", "content": "What should I plant?"}],
            persona=(
                "Be kind.\n\nActive specialist mode: LYLA "
                "(Companion and coordinator).\n"
                f"{get_agent('lyla').instructions}"
            ),
            memories=["The user likes gardening."],
            focus="plan a garden",
        )
        self.assertEqual(reply, "Let's start with herbs.")
        self.assertEqual(len(mind.history), 2)

    def test_selected_specialist_mode_adds_its_instructions(self):
        manager = ConversationManager(soul=SoulMemory(), mind=MindMemory())
        with patch(
            "src.conversation_manager.generate_from_messages",
            return_value="I found a likely issue.",
        ) as generate:
            manager.ask("Review this code.", agent_id="edith")

        persona = generate.call_args.kwargs["persona"]
        self.assertIn("Active specialist mode: EDITH", persona)
        self.assertIn("defensive review", persona)
        self.assertIn("You cannot scan systems", persona)

    def test_default_routing_selects_specialist_for_coding_request(self):
        manager = ConversationManager(soul=SoulMemory(), mind=MindMemory())
        with patch(
            "src.conversation_manager.generate_from_messages",
            return_value="Here is a code suggestion.",
        ) as generate:
            manager.ask("Can you debug this Python script?")

        persona = generate.call_args.kwargs["persona"]
        self.assertIn("Active specialist mode: JARVIS", persona)
        self.assertIn("You do not have direct file or command access", persona)

    def test_unknown_specialist_mode_is_rejected_before_generation(self):
        manager = ConversationManager(soul=SoulMemory(), mind=MindMemory())
        with patch("src.conversation_manager.generate_from_messages") as generate:
            with self.assertRaisesRegex(ValueError, "Unknown LYLA agent"):
                manager.ask("Hello", agent_id="unknown")
        generate.assert_not_called()
        self.assertEqual(manager.mind.history, [])

    def test_failed_generation_does_not_pollute_mind(self):
        manager = ConversationManager(soul=SoulMemory(), mind=MindMemory())
        with patch(
            "src.conversation_manager.generate_from_messages",
            side_effect=RuntimeError("model failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "model failed"):
                manager.ask("hello")
        self.assertEqual(manager.mind.history, [])

    def test_constructing_manager_does_not_load_model(self):
        with patch("src.lyla_core.text_pipeline._get_model") as get_model:
            ConversationManager(soul=SoulMemory(), mind=MindMemory())
        get_model.assert_not_called()

    def test_canned_exchange_is_recorded_in_the_short_term_mind(self):
        mind = MindMemory()
        manager = ConversationManager(soul=SoulMemory(), mind=mind)

        manager.remember_exchange("hello", "Hi there.")

        self.assertEqual(
            mind.history,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "Hi there."},
            ],
        )


if __name__ == "__main__":
    unittest.main()
