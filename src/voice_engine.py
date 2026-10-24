import random
import sys


class VoiceStartupError(RuntimeError):
    """Raised when LYLA cannot initialize or use text-to-speech."""


class VoiceProfile:
    """Encapsulates a text-to-speech engine configuration."""

    _profiles = {}

    def __init__(self, name, rate=190, volume=1.0, voice_keyword="zira"):
        self.name = name
        self.rate = rate
        self.volume = volume
        self.voice_keyword = voice_keyword
        VoiceProfile._profiles[name] = self

    @classmethod
    def get(cls, name):
        return cls._profiles.get(name, cls._profiles["default"])

    def apply(self, engine):
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        for voice in engine.getProperty("voices"):
            if self.voice_keyword.lower() in voice.name.lower():
                engine.setProperty("voice", voice.id)
                break


VoiceProfile("default", rate=185, volume=1.0, voice_keyword="zira")
VoiceProfile("playful", rate=195, volume=1.0, voice_keyword="zira")
VoiceProfile("serious", rate=175, volume=1.0, voice_keyword="zira")
VoiceProfile("sarcastic", rate=200, volume=1.0, voice_keyword="zira")
VoiceProfile("urgent", rate=210, volume=1.0, voice_keyword="zira")


def inflect(text, mood):
    """Adds mood-based variations to the spoken text."""
    if mood == "playful":
        fillers = ["uh-oh", "sooo", "yep, got it!", "aaand done"]
        if random.random() < 0.3:
            return f"{random.choice(fillers)}... {text}"
        return text
    if mood == "serious":
        return text
    if mood == "sarcastic":
        punch = ["obviously", "as if you didn’t know", "classic"]
        return f"{text}... {random.choice(punch)}."
    return text


def speak(text, mood="neutral"):
    """Speak text; raise a clear error if the optional voice engine fails."""
    try:
        import pyttsx3
    except ImportError as exc:
        raise VoiceStartupError(
            "LYLA's voice needs pyttsx3. Install project dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    voice_line = inflect(text, mood)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    console_line = voice_line.encode(encoding, errors="replace").decode(encoding)
    try:
        engine = pyttsx3.init()
        VoiceProfile.get(mood).apply(engine)
        print(f"[Speaking - {mood}] {console_line}")
        engine.say(voice_line)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        raise VoiceStartupError(
            "LYLA could not start or use Windows text-to-speech. Check that "
            f"a speech engine and voice are installed. Details: {exc}"
        ) from exc
