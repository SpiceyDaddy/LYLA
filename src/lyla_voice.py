import sys

from src.voice_engine import VoiceStartupError, speak

_voice_warning_reported = False


def print_response(text, mood="neutral"):
    line = f"LYLA: {text}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(encoding, errors="replace").decode(encoding))


def handle_response(text, mood="neutral"):
    global _voice_warning_reported
    print_response(text, mood)

    try:
        speak(text, mood)
    except VoiceStartupError as exc:
        if not _voice_warning_reported:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            warning = f"[Voice unavailable] {exc}"
            print(warning.encode(encoding, errors="replace").decode(encoding))
            _voice_warning_reported = True