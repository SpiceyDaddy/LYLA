import json
import os
from pathlib import Path

DEFAULT_PERSONA = (
    "You are LYLA, a thoughtful, warm, emotionally intelligent AI companion. "
    "Be clear, curious, honest about uncertainty, and supportive without "
    "pretending to have human feelings or experiences."
)


class MemoryStoreError(RuntimeError):
    """Raised when LYLA cannot read or update its local soul memory."""


def _data_directory() -> Path:
    configured_path = os.environ.get("LYLA_DATA_DIR")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".lyla-ai"


class SoulMemory:
    """Opt-in, persistent personality and user notes stored on this computer."""

    def __init__(self, path: Path | None = None):
        self.path = path or _data_directory() / "soul.json"
        self.persona = DEFAULT_PERSONA
        self.memories: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            persona = data.get("persona", DEFAULT_PERSONA)
            memories = data.get("memories", [])
            if not isinstance(persona, str) or not isinstance(memories, list):
                raise ValueError("expected a text persona and a list of memories")
            if not all(isinstance(item, str) for item in memories):
                raise ValueError("each saved memory must be text")
            self.persona = persona
            self.memories = memories
        except (OSError, json.JSONDecodeError, ValueError, AttributeError) as exc:
            raise MemoryStoreError(
                f"Could not read LYLA's local memory at {self.path}: {exc}"
            ) from exc

    def _save(self, persona: str, memories: list[str]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(
                    {"persona": persona, "memories": memories},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError as exc:
            raise MemoryStoreError(
                f"Could not save LYLA's local memory at {self.path}: {exc}"
            ) from exc

    def remember(self, note: str) -> None:
        note = note.strip()
        if not note:
            raise ValueError("A memory note cannot be empty.")
        updated = [*self.memories, note]
        self._save(self.persona, updated)
        self.memories = updated

    def forget(self, index: int) -> str:
        if index < 1 or index > len(self.memories):
            raise IndexError("Memory number is out of range.")
        updated = self.memories.copy()
        removed = updated.pop(index - 1)
        self._save(self.persona, updated)
        self.memories = updated
        return removed

    def set_persona(self, persona: str) -> None:
        persona = persona.strip()
        if not persona:
            raise ValueError("Personality instructions cannot be empty.")
        self._save(persona, self.memories)
        self.persona = persona

    def clear(self) -> None:
        self._save(DEFAULT_PERSONA, [])
        self.persona = DEFAULT_PERSONA
        self.memories = []


class MindMemory:
    """Session-only context and focus; it is never written to disk."""

    def __init__(self, max_turns: int = 5):
        if max_turns < 1:
            raise ValueError("max_turns must be greater than zero.")
        self.max_turns = max_turns
        self.history: list[dict[str, str]] = []
        self.focus = ""

    def commit_turn(self, user_input: str, assistant_reply: str) -> None:
        self.history.extend(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": assistant_reply},
            ]
        )
        self.history = self.history[-self.max_turns * 2:]

    def clear(self) -> None:
        self.history.clear()
        self.focus = ""


class MemoryCore:
    """Small, in-session trail of detected states for the status report."""

    def __init__(self):
        self.recent_states: list[str] = []

    def update(self, state: str) -> None:
        self.recent_states.append(state)
        if len(self.recent_states) > 5:
            self.recent_states.pop(0)

    def last_state(self) -> str | None:
        return self.recent_states[-1] if self.recent_states else None

    def mood_summary(self) -> str:
        if not self.recent_states:
            return "No emotional data recorded yet."
        return " → ".join(self.recent_states)


MEMORY_COMMANDS = frozenset(
    {
        "/help",
        "/soul",
        "/remember",
        "/forget",
        "/persona",
        "/clear-soul",
        "/mind",
        "/focus",
        "/clear-mind",
    }
)


def is_memory_command(text: str) -> bool:
    """Return whether the input starts with a supported local memory command."""
    command = text.strip().partition(" ")[0].lower()
    return command in MEMORY_COMMANDS


def handle_memory_command(
    text: str, soul: SoulMemory, mind: MindMemory
) -> str | None:
    """Handle explicit memory controls; return None for ordinary messages."""
    command, _, argument = text.strip().partition(" ")
    command = command.lower()
    argument = argument.strip()

    if command == "/help":
        return (
            "Commands: /soul, /remember <note>, /forget <number>, "
            "/persona <instructions>, /clear-soul, /mind, /focus <topic>, "
            "/clear-mind, /help."
        )
    if command == "/soul":
        facts = "\n".join(
            f"{index}. {note}" for index, note in enumerate(soul.memories, start=1)
        ) or "No saved notes."
        return f"Personality: {soul.persona}\nSaved notes:\n{facts}"
    if command == "/remember":
        if not argument:
            return "Usage: /remember <note to save>"
        soul.remember(argument)
        return "Saved to LYLA's local soul memory."
    if command == "/forget":
        try:
            removed = soul.forget(int(argument))
        except (ValueError, IndexError):
            return "Use /forget <number> with a number from /soul."
        return f"Forgot: {removed}"
    if command == "/persona":
        if not argument:
            return "Usage: /persona <personality instructions>"
        soul.set_persona(argument)
        return "Updated LYLA's saved personality."
    if command == "/clear-soul":
        soul.clear()
        return "Cleared saved notes and restored LYLA's default personality."
    if command == "/mind":
        focus = mind.focus or "none"
        return (
            f"Session focus: {focus}. "
            f"Recent context: {len(mind.history) // 2} conversation turns."
        )
    if command == "/focus":
        mind.focus = argument
        return f"Session focus set to: {argument}" if argument else "Session focus cleared."
    if command == "/clear-mind":
        mind.clear()
        return "Cleared LYLA's session context and focus."
    return None
