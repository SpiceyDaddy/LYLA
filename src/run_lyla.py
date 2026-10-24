# src/run_lyla.py

from lyla_core.text_pipeline import generate_from_prompt
from voice_engine            import speak

def main():
    print("LYLA: I’m here and listening. (type 'exit' to quit)")

    while True:
        user_text = input("You: ").strip()
        if user_text.lower() in ("exit", "quit"):
            speak("Farewell, brave soul. Until next time.", mood="serious")
            break

        # Route everything through the new pipeline
        lyla_reply = generate_from_prompt(user_text, truncate_length=200)

        # Simple mood heuristic
        mood = "playful" if any(k in user_text.lower() for k in ("joke", "lol", "?")) else "neutral"
        speak(lyla_reply, mood=mood)

if __name__ == "__main__":
    main()