import json
import unittest
from unittest.mock import patch

from src.voicebox_client import VoiceboxClient, VoiceboxError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


class VoiceboxClientTests(unittest.TestCase):
    def test_rejects_non_local_voicebox_urls(self):
        for url in (
            "https://127.0.0.1:17493",
            "http://voicebox.example:17493",
            "http://127.0.0.1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                VoiceboxClient(base_url=url)

    def test_connection_requires_local_speak_endpoint(self):
        response = FakeResponse(
            json.dumps({"paths": {"/speak": {}}}).encode("utf-8")
        )
        with patch("src.voicebox_client.urlopen", return_value=response) as open_url:
            VoiceboxClient().check_connection()
        self.assertEqual(open_url.call_args.args[0].full_url, "http://127.0.0.1:17493/openapi.json")

    def test_sends_speech_request_to_selected_local_profile(self):
        generation = {"id": "gen-123", "status": "completed"}
        response = FakeResponse(json.dumps(generation).encode("utf-8"))
        with patch("src.voicebox_client.urlopen", return_value=response) as open_url:
            result = VoiceboxClient(profile="LYLA Voice").speak("Hello there.")

        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:17493/speak")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"text": "Hello there.", "profile": "LYLA Voice"},
        )
        self.assertEqual(result, "Voicebox finished speaking.")

    def test_waits_for_generation_completion(self):
        start_response = FakeResponse(
            json.dumps({"id": "gen-123", "status": "generating"}).encode("utf-8")
        )
        status_response = FakeResponse(
            b'data: {"id":"gen-123","status":"completed"}\n\n'
        )
        with patch(
            "src.voicebox_client.urlopen",
            side_effect=[start_response, status_response],
        ) as open_url:
            result = VoiceboxClient().speak("Testing.")

        self.assertEqual(result, "Voicebox finished speaking.")
        self.assertEqual(
            open_url.call_args_list[1].args[0].full_url,
            "http://127.0.0.1:17493/generate/gen-123/status",
        )

    def test_reports_missing_voicebox_server(self):
        with patch(
            "src.voicebox_client.urlopen",
            side_effect=OSError("connection refused"),
        ):
            with self.assertRaisesRegex(VoiceboxError, "Open the Voicebox desktop app"):
                VoiceboxClient().check_connection()


if __name__ == "__main__":
    unittest.main()
