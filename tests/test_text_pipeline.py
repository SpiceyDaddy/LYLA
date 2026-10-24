import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.lyla_core import text_pipeline


class FakeModel:
    def __init__(self, message):
        self.message = message
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"choices": [{"message": self.message}]}


class FakeTokenizerModel:
    def tokenize(self, prompt, add_bos=False):
        return list(prompt)

    def detokenize(self, tokens):
        return bytes(tokens)


class TextPipelineTests(unittest.TestCase):
    def test_model_filename_matches_hugging_face_repository(self):
        self.assertEqual(
            text_pipeline.MODEL_FILE,
            "Qwen_Qwen3-14B-Q5_K_M.gguf",
        )

    def test_model_loading_uses_chat_template_from_gguf_metadata(self):
        class FakeLlama:
            @staticmethod
            def from_pretrained(**kwargs):
                return kwargs

        with tempfile.TemporaryDirectory() as cache_dir:
            with patch.object(text_pipeline, "_llm", None):
                with patch.object(
                    text_pipeline, "MODEL_CACHE_DIR", text_pipeline.Path(cache_dir)
                ):
                    with patch.dict(
                        sys.modules,
                        {"llama_cpp": SimpleNamespace(Llama=FakeLlama)},
                    ):
                        model_options = text_pipeline._get_model()

        self.assertNotIn("chat_format", model_options)
        self.assertEqual(model_options["filename"], text_pipeline.MODEL_FILE)
        self.assertEqual(model_options["n_ctx"], 8192)
        self.assertEqual(model_options["n_threads"], text_pipeline.MODEL_THREADS)
        self.assertEqual(
            model_options["n_threads_batch"], text_pipeline.MODEL_THREADS
        )

    def test_generation_uses_bounded_response_length(self):
        model = FakeModel({"role": "assistant", "content": "Hello."})
        with patch.object(text_pipeline, "_get_model", return_value=model):
            text_pipeline.generate_from_messages(
                [{"role": "user", "content": "Hi"}]
            )

        self.assertEqual(
            model.calls[0]["max_tokens"],
            text_pipeline.MAX_RESPONSE_TOKENS,
        )

    def test_generation_removes_qwen_thinking_block(self):
        model = FakeModel(
            {
                "role": "assistant",
                "content": (
                    "<think>Private deliberation about the prompt.</think>"
                    "Hello! I am LYLA."
                ),
            }
        )
        with patch.object(text_pipeline, "_get_model", return_value=model):
            result = text_pipeline.generate_from_messages(
                [{"role": "user", "content": "Introduce yourself."}]
            )

        self.assertEqual(result, "Hello! I am LYLA.")
        system_prompt = model.calls[0]["messages"][0]["content"]
        self.assertIn("never output private reasoning", system_prompt)
        self.assertIn("only explicitly saved Soul notes", system_prompt)

    def test_generation_drops_unclosed_thinking_block(self):
        model = FakeModel(
            {
                "role": "assistant",
                "content": "Visible preface.<think>private deliberation",
            }
        )
        with patch.object(text_pipeline, "_get_model", return_value=model):
            result = text_pipeline.generate_from_messages(
                [{"role": "user", "content": "Hi"}]
            )

        self.assertEqual(result, "Visible preface.")

    def test_generation_rejects_thinking_without_user_facing_answer(self):
        model = FakeModel(
            {
                "role": "assistant",
                "content": "<think>Only private deliberation.</think>",
            }
        )
        with patch.object(text_pipeline, "_get_model", return_value=model):
            with self.assertRaisesRegex(
                text_pipeline.ModelGenerationError,
                "reasoning without a user-facing answer",
            ):
                text_pipeline.generate_from_messages(
                    [{"role": "user", "content": "Hi"}]
                )

    def test_system_prompt_includes_soul_notes_and_session_focus(self):
        model = FakeModel({"role": "assistant", "content": "Hello."})
        with patch.object(text_pipeline, "_get_model", return_value=model):
            result = text_pipeline.generate_from_messages(
                [{"role": "user", "content": "Hi"}],
                persona="Be thoughtful.",
                memories=["The user likes music."],
                focus="discuss a concert",
            )

        self.assertEqual(result, "Hello.")
        system_message = model.calls[0]["messages"][0]["content"]
        self.assertIn("Be thoughtful.", system_message)
        self.assertIn("The user likes music.", system_message)
        self.assertIn("discuss a concert", system_message)

    def test_chat_completion_returns_only_response_content(self):
        model = FakeModel(
            {"role": "assistant", "content": "The answer is 42."}
        )
        with patch.object(text_pipeline, "_get_model", return_value=model):
            result = text_pipeline.generate_from_messages(
                [{"role": "user", "content": "What is the answer?"}]
            )

        self.assertEqual(result, "The answer is 42.")
        self.assertNotIn("What is the answer?", result)

    def test_single_prompt_helper_truncates_and_returns_response(self):
        with patch.object(
            text_pipeline, "_get_model", return_value=FakeTokenizerModel()
        ):
            with patch.object(
                text_pipeline,
                "generate_from_messages",
                return_value="new response",
            ) as generate:
                result = text_pipeline.generate_from_prompt(
                    "abcdefgh", truncate_length=3
                )

        self.assertEqual(result, "new response")
        generate.assert_called_once_with([{"role": "user", "content": "fgh"}])

    def test_model_loading_failure_has_actionable_message(self):
        original_import = __import__

        def fail_llama_import(name, *args, **kwargs):
            if name == "llama_cpp":
                raise ModuleNotFoundError("missing llama-cpp-python")
            return original_import(name, *args, **kwargs)

        with patch.object(text_pipeline, "_llm", None):
            with patch("builtins.__import__", side_effect=fail_llama_import):
                with self.assertRaises(text_pipeline.ModelStartupError) as error:
                    text_pipeline._get_model()
        self.assertIn("llama-cpp-python", str(error.exception))
        self.assertIn(text_pipeline.MODEL_FILE, str(error.exception))

    def test_generation_failure_has_clear_error(self):
        model = FakeModel({})
        model.create_chat_completion = lambda **kwargs: (_ for _ in ()).throw(
            OSError("runtime unavailable")
        )
        with patch.object(text_pipeline, "_get_model", return_value=model):
            with self.assertRaises(text_pipeline.ModelGenerationError) as error:
                text_pipeline.generate_from_messages(
                    [{"role": "user", "content": "Hi"}]
                )
        self.assertIn("failed while generating", str(error.exception))


if __name__ == "__main__":
    unittest.main()
