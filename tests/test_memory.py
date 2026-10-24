import tempfile
import unittest
from pathlib import Path

from src.memory import (
    DEFAULT_PERSONA,
    MindMemory,
    SoulMemory,
    handle_memory_command,
)


class MemoryTests(unittest.TestCase):
    def test_soul_is_opt_in_persistent_and_clearable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soul.json"
            soul = SoulMemory(path)
            self.assertFalse(path.exists())

            soul.remember("I prefer concise answers.")
            soul.set_persona("Be calm and direct.")
            loaded = SoulMemory(path)
            self.assertEqual(loaded.memories, ["I prefer concise answers."])
            self.assertEqual(loaded.persona, "Be calm and direct.")

            loaded.clear()
            reset = SoulMemory(path)
            self.assertEqual(reset.memories, [])
            self.assertEqual(reset.persona, DEFAULT_PERSONA)

    def test_forget_command_removes_selected_note(self):
        with tempfile.TemporaryDirectory() as directory:
            soul = SoulMemory(Path(directory) / "soul.json")
            mind = MindMemory()
            soul.remember("first")
            soul.remember("second")

            result = handle_memory_command("/forget 1", soul, mind)

            self.assertEqual(result, "Forgot: first")
            self.assertEqual(soul.memories, ["second"])

    def test_mind_is_session_only_and_focus_can_be_cleared(self):
        mind = MindMemory(max_turns=1)
        mind.commit_turn("old", "old reply")
        mind.commit_turn("new", "new reply")
        mind.focus = "finish the test"
        self.assertEqual(mind.history, [
            {"role": "user", "content": "new"},
            {"role": "assistant", "content": "new reply"},
        ])

        self.assertEqual(
            handle_memory_command("/focus", SoulMemory(Path("unused.json")), mind),
            "Session focus cleared.",
        )
        self.assertEqual(mind.focus, "")

        self.assertEqual(
            handle_memory_command("/clear-mind", SoulMemory(Path("unused.json")), mind),
            "Cleared LYLA's session context and focus.",
        )
        self.assertEqual(mind.history, [])


if __name__ == "__main__":
    unittest.main()
