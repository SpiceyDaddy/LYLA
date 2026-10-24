import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_VOICEBOX_URL = "http://127.0.0.1:17493"
SPEAK_TIMEOUT_SECONDS = 180


class VoiceboxError(RuntimeError):
    """Raised when LYLA cannot communicate with the local Voicebox app."""


class VoiceboxClient:
    def __init__(
        self,
        base_url: str = DEFAULT_VOICEBOX_URL,
        profile: str = "",
        timeout: float = 10,
    ):
        parsed_url = urlparse(base_url)
        if (
            parsed_url.scheme != "http"
            or parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed_url.port is None
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError("Voicebox must use an HTTP localhost URL.")
        self.base_url = base_url.rstrip("/")
        self.profile = profile.strip()
        self.timeout = timeout

    def check_connection(self) -> None:
        request = Request(f"{self.base_url}/openapi.json")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                specification = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise VoiceboxError(
                "Could not connect to Voicebox at "
                f"{self.base_url}. Open the Voicebox desktop app first. "
                f"Details: {exc}"
            ) from exc
        if "/speak" not in specification.get("paths", {}):
            raise VoiceboxError(
                "The running Voicebox server does not expose the /speak API."
            )

    def speak(self, text: str) -> str:
        if not text.strip():
            raise ValueError("There is no reply text to speak.")
        payload = {"text": text}
        if self.profile:
            payload["profile"] = self.profile
        request = Request(
            f"{self.base_url}/speak",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                generation = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise VoiceboxError(f"Voicebox rejected the speech request: {detail}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise VoiceboxError(
                "Could not send speech to Voicebox. Check that the Voicebox "
                f"app is open. Details: {exc}"
            ) from exc

        generation_id = generation.get("id")
        if not generation_id:
            raise VoiceboxError("Voicebox returned a response without a generation ID.")
        status = generation.get("status", "generating")
        if status == "failed":
            raise VoiceboxError(
                f"Voicebox failed to generate speech: {generation.get('error') or 'unknown error'}"
            )
        if status == "completed":
            return "Voicebox finished speaking."
        return self._wait_for_generation(generation_id)

    def _wait_for_generation(self, generation_id: str) -> str:
        request = Request(
            f"{self.base_url}/generate/{quote(generation_id, safe='')}/status",
            headers={"Accept": "text/event-stream"},
        )
        deadline = time.monotonic() + SPEAK_TIMEOUT_SECONDS
        try:
            with urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    if time.monotonic() >= deadline:
                        raise VoiceboxError(
                            "Voicebox speech generation timed out. Check the "
                            "Voicebox app for model or audio errors."
                        )
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        update = json.loads(line[5:].strip())
                    except json.JSONDecodeError as exc:
                        raise VoiceboxError(
                            "Voicebox returned an invalid generation status."
                        ) from exc
                    status = update.get("status")
                    if status == "completed":
                        return "Voicebox finished speaking."
                    if status == "failed":
                        raise VoiceboxError(
                            "Voicebox failed to generate speech: "
                            f"{update.get('error') or 'unknown error'}"
                        )
                    if status == "not_found":
                        raise VoiceboxError(
                            "Voicebox could not find the speech generation."
                        )
        except VoiceboxError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise VoiceboxError(
                f"Could not read speech status from Voicebox: {exc}"
            ) from exc
        raise VoiceboxError("Voicebox closed the generation status stream unexpectedly.")
