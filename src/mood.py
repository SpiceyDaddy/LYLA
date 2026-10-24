import time

class MoodEngine:
    def __init__(self):
        self.last_state = None
        self.repetition_count = 0
        self.last_time = time.time()
        self.last_input = None

    def mood_comment(self):
        if self.repetition_count >= 3:
            return "Sensing a loop. Emotional drift detected."
        return "Mood stable. No anomalies."

    def update(self, input_text):
        if input_text == self.last_input:
            self.repetition_count += 1
        else:
            self.repetition_count = 1
            self.last_input = input_text
            self.last_time = time.time()

    def drift_response(self):
        if self.repetition_count >= 3 and self.last_input:
            return f"You’ve said '{self.last_input}' a few times... want to shift gears?"

    def uptime(self):
        seconds = int(time.time() - self.last_time)
        minutes = seconds // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit} since last emotional shift."

# ✅ Mood detection for voice responses (including LLM state)
def detect_mood(state):
    mood_map = {
        "Engage": "playful",
        "Celebrate": "playful",
        "Report": "serious",
        "Support": "sarcastic",
        "Farewell": "serious",
        "Reflect": "neutral",
        "LLM": "neutral",  # generative fallback state mood
    }
    return mood_map.get(state, "neutral")