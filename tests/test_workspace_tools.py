from pathlib import Path
import tempfile
import unittest

from src.workspace_tools import WorkspaceAssistant


class WorkspaceAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.assistant = WorkspaceAssistant(self.root)
        (self.root / "src").mkdir()
        self.file_path = self.root / "src" / "example.py"
        self.file_path.write_bytes(b"value = 1\r\n")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_reads_a_workspace_relative_utf8_file(self):
        result = self.assistant.read_file("src/example.py")
        self.assertEqual(result["path"], "src/example.py")
        self.assertEqual(result["content"], "value = 1\n")
        self.assertEqual(len(result["sha256"]), 64)

    def test_rejects_absolute_and_parent_traversal_paths(self):
        for path in ("../outside.txt", str(self.root / "src" / "example.py")):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.assistant.read_file(path)

    def test_edit_requires_preview_and_one_time_approval(self):
        preview = self.assistant.preview_change(
            "src/example.py",
            "value = 2\n",
        )
        self.assertIn("-value = 1", preview["diff"])
        self.assertIn("+value = 2", preview["diff"])
        self.assertEqual(self.file_path.read_text(encoding="utf-8"), "value = 1\n")

        result = self.assistant.apply_change(preview["approval_token"])
        self.assertEqual(result, {"path": "src/example.py", "status": "applied"})
        self.assertEqual(self.file_path.read_text(encoding="utf-8"), "value = 2\n")
        self.assertEqual(self.file_path.read_bytes(), b"value = 2\r\n")
        with self.assertRaisesRegex(ValueError, "missing or expired"):
            self.assistant.apply_change(preview["approval_token"])

    def test_stale_file_cannot_be_overwritten_by_an_old_preview(self):
        preview = self.assistant.preview_change("src/example.py", "value = 2\n")
        self.file_path.write_text("value = 3\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            self.assistant.apply_change(preview["approval_token"])
        self.assertEqual(self.file_path.read_text(encoding="utf-8"), "value = 3\n")

    def test_preview_can_create_a_file_in_an_existing_directory(self):
        preview = self.assistant.preview_change("src/new.py", "answer = 42\n")
        self.assertFalse(preview["no_change"])
        self.assistant.apply_change(preview["approval_token"])
        self.assertEqual(
            (self.root / "src" / "new.py").read_text(encoding="utf-8"),
            "answer = 42\n",
        )

    def test_identical_content_does_not_create_an_approval(self):
        content = self.assistant.read_file("src/example.py")["content"]
        preview = self.assistant.preview_change("src/example.py", content)
        self.assertTrue(preview["no_change"])
        self.assertEqual(preview["approval_token"], "")

    def test_rejects_binary_files_and_large_content(self):
        binary_file = self.root / "src" / "image.bin"
        binary_file.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.assistant.read_file("src/image.bin")
        with self.assertRaisesRegex(ValueError, "1 MB"):
            self.assistant.preview_change("src/example.py", "x" * 1_048_577)

    def test_runs_only_the_workspace_python_test_suite(self):
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_smoke.py").write_text(
            "import unittest\n\n"
            "class SmokeTests(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        result = self.assistant.run_tests()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("OK", result["output"])


if __name__ == "__main__":
    unittest.main()
