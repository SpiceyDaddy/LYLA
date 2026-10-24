# src/conversation_manager.py

from src.lyla_core.text_pipeline import generate_from_messages
from src.memory import MindMemory, SoulMemory
from src.agents import get_agent, route_agent_id

class ConversationManager:
    """
    Keeps a rolling chat history and routes requests through the local model.
    """

    def __init__(
        self,
        max_history: int = 5,
        soul: SoulMemory | None = None,
        mind: MindMemory | None = None,
    ):
        self.soul = soul or SoulMemory()
        self.mind = mind or MindMemory(max_turns=max_history)

    def ask(
        self, user_input: str, agent_id: str | None = None
    ) -> tuple[str, None]:
        """
        Append the user's input to history and get a local model response.
        Returns (reply, None) for compatibility with existing call sites.
        """
        messages = [
            *self.mind.history,
            {"role": "user", "content": user_input},
        ]
        agent = get_agent(
            route_agent_id(user_input) if agent_id is None else agent_id
        )
        persona = (
            f"{self.soul.persona}\n\nActive specialist mode: "
            f"{agent.name} ({agent.role}).\n{agent.instructions}"
        )
        reply = generate_from_messages(
            messages,
            persona=persona,
            memories=self.soul.memories,
            focus=self.mind.focus,
        )
        self.remember_exchange(user_input, reply)

        return reply, None

    def remember_exchange(self, user_input: str, assistant_reply: str) -> None:
        """Add a completed turn to the session-only mind context."""
        self.mind.commit_turn(user_input, assistant_reply)