# src/lyla.py

from src.lyla_voice import handle_response
from src.tone_engine import respond
from src.scene_library import bootup_scene
from src.memory import (
    MemoryCore,
    MindMemory,
    SoulMemory,
    handle_memory_command,
)
from src.mood import MoodEngine, detect_mood  # detect_mood now covers "LLM"
from src.state_engine import get_state
from src.conversation_manager import ConversationManager
from src.lyla_core.text_pipeline import LocalModelError

def main():
    memory = MemoryCore()
    soul = SoulMemory()
    mind = MindMemory()
    mood = MoodEngine()
    convo = ConversationManager(soul=soul, mind=mind)

    # Bootup sequence
    for line in bootup_scene():
        handle_response(line, "playful")

    # Interaction loop
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        command_reply = handle_memory_command(user_input, soul, mind)
        if command_reply is not None:
            handle_response(command_reply, "neutral")
            continue

        # Update drift engine
        mood.update(user_input)
        drift = mood.drift_response()
        if drift:
            handle_response(drift, "neutral")

        # Core state detection
        state = get_state(user_input)
        previous_state = memory.last_state()

        # Route based on state
        if state == "LLM":
            try:
                reply, _ = convo.ask(user_input)
            except LocalModelError as exc:
                handle_response(str(exc), "serious")
                continue
        else:
            reply = respond(user_input, state)
            convo.remember_exchange(user_input, reply)

        # Track state in memory
        memory.update(state)

        # If re-engaging after another state
        if state == "Engage":
            if previous_state and previous_state != "Engage":
                handle_response(
                    f"Still feeling that {previous_state} energy, James.",
                    detect_mood("Engage")
                )

        # Main reply routed through mood detection
        handle_response(reply, detect_mood(state))

        # Extended status report
        if state == "Report":
            trail   = memory.mood_summary()
            uptime  = mood.uptime()
            comment = mood.mood_comment()
            handle_response(f"Emotional trail: {trail}", detect_mood("Report"))
            handle_response(uptime,              detect_mood("Report"))
            handle_response(comment,             detect_mood("Report"))

        # Exit condition
        if state == "Farewell":
            handle_response(
                "Mythic Core disengaged. Safe travels, James.",
                detect_mood("Farewell")
            )
            break

if __name__ == "__main__":
    main()