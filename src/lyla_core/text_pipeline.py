from datetime import datetime
import os
from pathlib import Path
import re

MODEL_REPO = "bartowski/Qwen_Qwen3-14B-GGUF"
MODEL_FILE = "Qwen_Qwen3-14B-Q5_K_M.gguf"
MODEL_CACHE_DIR = Path(
    os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
) / "hub"
MODEL_THREADS = min(os.cpu_count() or 8, 12)
MODEL_CONTEXT = 8192
MAX_RESPONSE_TOKENS = 384
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = (
    "You are running locally on the user's computer. Speak clearly and "
    "naturally. Give only the concise, user-facing answer; never output "
    "private reasoning, deliberation, or <think> tags. Do not claim that "
    "conversation data is never stored or shared. Session context stays in "
    "memory while LYLA is running, and only explicitly saved Soul notes and "
    "personality persist locally. Use the get_time tool when the user asks "
    "for the current local date or time."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current local date and time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
]

_llm = None


def is_model_loaded() -> bool:
    """Return whether local model weights are currently loaded in memory."""
    return _llm is not None


class LocalModelError(RuntimeError):
    """Base error for model loading and generation failures."""


class ModelStartupError(LocalModelError):
    """Raised when LYLA cannot load its local model."""


class ModelGenerationError(LocalModelError):
    """Raised when the local model fails while generating a response."""


def _user_facing_content(content: str) -> str:
    """Remove Qwen reasoning sections, returning only the final answer."""
    closing_tag = "</think>"
    opening_match = re.search(r"<think\s*>", content, flags=re.IGNORECASE)
    closing_matches = list(
        re.finditer(re.escape(closing_tag), content, flags=re.IGNORECASE)
    )

    if closing_matches:
        content = content[closing_matches[-1].end():]
    elif opening_match:
        content = content[:opening_match.start()]

    content = re.sub(r"</?think\s*>", "", content, flags=re.IGNORECASE)
    return content.strip()


def _get_model():
    global _llm
    if _llm is None:
        try:
            from llama_cpp import Llama

            MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _llm = Llama.from_pretrained(
                repo_id=MODEL_REPO,
                filename=MODEL_FILE,
                cache_dir=str(MODEL_CACHE_DIR),
                n_ctx=MODEL_CONTEXT,
                n_gpu_layers=0,
                n_threads=MODEL_THREADS,
                n_threads_batch=MODEL_THREADS,
                verbose=False,
            )
        except Exception as exc:
            raise ModelStartupError(
                "Could not start LYLA's local Qwen model "
                f"({MODEL_REPO}/{MODEL_FILE}). Check that llama-cpp-python is "
                "installed, internet access is available for the first "
                f"download, and the model cache has enough disk space: "
                f"{MODEL_CACHE_DIR}. Details: {exc}"
            ) from exc
    return _llm


def get_time() -> str:
    return datetime.now().isoformat()


def generate_from_messages(
    messages: list[dict[str, str]],
    *,
    persona: str | None = None,
    memories: list[str] | None = None,
    focus: str = "",
) -> str:
    """Generate a local response using session context and explicit soul notes."""
    system_content = persona or (
        "You are LYLA, a thoughtful, warm, emotionally intelligent AI companion."
    )
    system_content = f"{system_content}\n\n{SYSTEM_PROMPT}"
    if memories:
        saved_notes = "\n".join(f"- {note}" for note in memories)
        system_content += (
            "\n\nThe user explicitly saved these notes for long-term memory. "
            "Use them only when relevant:\n" + saved_notes
        )
    if focus:
        system_content += f"\n\nCurrent session focus: {focus}"

    conversation = [{"role": "system", "content": system_content}, *messages]
    model = _get_model()

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = model.create_chat_completion(
                messages=conversation,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.6,
                max_tokens=MAX_RESPONSE_TOKENS,
            )
        except Exception as exc:
            raise ModelGenerationError(
                f"LYLA's local model failed while generating a response: {exc}"
            ) from exc

        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ModelGenerationError(
                    "The local model returned an empty response."
                )
            answer = _user_facing_content(content)
            if not answer:
                raise ModelGenerationError(
                    "The local model returned reasoning without a "
                    "user-facing answer. Please try again."
                )
            return answer

        conversation.append(message)
        for call in tool_calls:
            name = call["function"]["name"]
            if name != "get_time":
                raise ModelGenerationError(
                    f"The local model requested unsupported tool: {name}"
                )
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": get_time(),
                }
            )

    raise ModelGenerationError(
        "The local model exceeded the maximum number of tool calls."
    )


def generate_from_prompt(prompt: str, truncate_length: int = 512) -> str:
    """Compatibility helper for callers that provide a single user prompt."""
    if truncate_length < 1:
        raise ValueError("truncate_length must be greater than zero.")

    model = _get_model()
    prompt_tokens = model.tokenize(prompt.encode("utf-8"), add_bos=False)
    if len(prompt_tokens) > truncate_length:
        prompt = model.detokenize(prompt_tokens[-truncate_length:]).decode(
            "utf-8", errors="replace"
        )

    return generate_from_messages([{"role": "user", "content": prompt}])
