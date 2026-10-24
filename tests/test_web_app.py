import json
import tempfile
import threading
import unittest
from email.message import Message
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from src import web_app
from src.defensive_scanner import DefensiveFileScanner
from src.lyla_core.text_pipeline import LocalModelError
from src.memory import MindMemory, SoulMemory
from src.task_tracker import ChatTaskTracker
from src.weather_client import AmbiguousWeatherLocation, OpenMeteoClient
from src.workspace_tools import WorkspaceAssistant


class FakeConversation:
    def __init__(self):
        self.calls = []

    def ask(self, message, agent_id="lyla"):
        self.calls.append((message, agent_id))
        return "A local answer.", None


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.temp_directory.name) / "desktop.json"
        self.workspace_root = Path(self.temp_directory.name) / "workspace"
        self.workspace_root.mkdir()
        (self.workspace_root / "src").mkdir()
        self.workspace_file = self.workspace_root / "src" / "example.py"
        self.workspace_file.write_text("value = 1\n", encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.LylaRequestHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.patches = [
            patch.object(web_app, "SETTINGS_PATH", self.settings_path),
            patch.object(web_app, "_soul", SoulMemory(Path(self.temp_directory.name) / "soul.json")),
            patch.object(web_app, "_mind", MindMemory()),
            patch.object(web_app, "_conversation", FakeConversation()),
            patch.object(web_app, "_task_tracker", ChatTaskTracker()),
            patch.object(
                web_app,
                "_workspace",
                WorkspaceAssistant(self.workspace_root),
            ),
            patch.object(web_app, "_weather", OpenMeteoClient()),
            patch.object(web_app, "_edith_scanner", DefensiveFileScanner()),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_directory.cleanup()

    def post_json(self, route, payload, headers=None):
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = Request(
            self.base_url + route,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_dashboard_page_is_served_from_supplied_html(self):
        with urlopen(self.base_url + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
        self.assertIn("LYLA // CORE SYSTEM", html)
        self.assertIn("TEXT WITH LYLA", html)
        for target in ("mod-agents", "mod-today", "mod-system", "mod-log", "mod-say"):
            self.assertIn(
                f'data-target="{target}" aria-pressed="true"',
                html,
            )
        self.assertIn(">Text</button>", html)
        self.assertIn("Speak latest reply", html)
        self.assertIn("AGENTS", html)
        self.assertIn('id="mod-agents"', html)
        self.assertIn("AUTOMATIC ROUTING", html)
        self.assertIn("AUTO-ROUTED", html)
        self.assertIn('id="sendBtn"', html)
        self.assertIn('id="speakLatestBtn"', html)
        self.assertIn('id="taskStatus"', html)
        self.assertNotIn("Use this mode", html)
        self.assertNotIn("agentSelect", html)
        self.assertIn("same local model", html)
        self.assertIn("--gold:#FF4FD8", html)
        self.assertIn("overflow-x:clip", html)
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn("JARVIS WORKSPACE", html)
        self.assertIn("workspaceApplyBtn", html)
        self.assertIn("workspaceTestsBtn", html)
        self.assertIn("fridayWeatherConsent", html)
        self.assertIn("edithScanConsent", html)
        self.assertIn("edithScanBtn", html)
        self.assertIn('data-target="mod-ultron" aria-pressed="true"', html)
        self.assertIn('id="ultronReviewInput"', html)
        self.assertIn('id="ultronReviewBtn"', html)

    def test_chat_api_returns_model_reply(self):
        status, result = self.post_json("/api/chat", {"message": "Hello LYLA"})
        self.assertEqual(status, 200)
        self.assertEqual(result["reply"], "A local answer.")
        self.assertEqual(result["agent"], "LYLA")
        self.assertEqual(result["agent_id"], "lyla")
        self.assertEqual(result["routing"], "automatic")
        self.assertEqual(result["task_status"], "completed")
        self.assertTrue(result["task_id"])
        self.assertEqual(
            web_app._conversation.calls,
            [("Hello LYLA", "lyla")],
        )

    def test_agents_api_lists_all_specialist_modes(self):
        with urlopen(self.base_url + "/api/agents", timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(
            [agent["id"] for agent in result["agents"]],
            ["lyla", "jarvis", "friday", "edith", "ultron"],
        )
        self.assertEqual(
            [agent["accent"] for agent in result["agents"]],
            ["#FF4FD8", "#159FE8", "#20D9C8", "#4D91FF", "#E5252A"],
        )

    def test_chat_api_routes_to_selected_specialist_mode(self):
        status, result = self.post_json(
            "/api/chat",
            {"message": "Review this code.", "agent_id": "edith"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["agent"], "EDITH")
        self.assertEqual(result["agent_id"], "edith")
        self.assertEqual(result["routing"], "manual")
        self.assertEqual(
            web_app._conversation.calls,
            [("Review this code.", "edith")],
        )

    def test_workspace_file_read_and_approved_change_flow(self):
        with urlopen(
            self.base_url + "/api/workspace/read?path=src%2Fexample.py",
            timeout=3,
        ) as response:
            loaded = json.loads(response.read().decode("utf-8"))
        self.assertEqual(loaded["content"], "value = 1\n")

        _status, preview = self.post_json(
            "/api/workspace/preview",
            {"path": "src/example.py", "content": "value = 2\n"},
        )
        self.assertIn("+value = 2", preview["diff"])
        self.assertEqual(self.workspace_file.read_text(encoding="utf-8"), "value = 1\n")
        _status, applied = self.post_json(
            "/api/workspace/apply",
            {"approval_token": preview["approval_token"]},
        )
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(self.workspace_file.read_text(encoding="utf-8"), "value = 2\n")

    def test_workspace_api_rejects_paths_outside_project(self):
        request = Request(
            self.base_url + "/api/workspace/read?path=..%2Foutside.txt",
            method="GET",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)

    def test_workspace_test_runner_requires_confirmation(self):
        request = Request(
            self.base_url + "/api/workspace/tests",
            data=json.dumps({"confirm": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with patch.object(web_app._workspace, "run_tests") as run_tests:
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)
        run_tests.assert_not_called()

    def test_workspace_test_runner_returns_captured_results(self):
        with patch.object(
            web_app._workspace,
            "run_tests",
            return_value={"status": "passed", "exit_code": 0, "output": "OK"},
        ) as run_tests:
            status, result = self.post_json(
                "/api/workspace/tests",
                {"confirm": True},
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "passed")
        run_tests.assert_called_once_with()

    def test_weather_lookup_requires_explicit_location_sharing_consent(self):
        with patch.object(web_app._weather, "get_forecast") as get_forecast:
            request = Request(
                self.base_url + "/api/weather",
                data=json.dumps(
                    {"location": "Jackson, Tennessee", "consent": False}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)
        get_forecast.assert_not_called()

    def test_weather_lookup_returns_sourced_forecast_data(self):
        forecast = {
            "location": "Jackson, Tennessee, United States",
            "current": {"temperature": 72},
            "daily": [],
            "sources": [{"name": "Open-Meteo forecast"}],
        }
        with patch.object(
            web_app._weather,
            "get_forecast",
            return_value=forecast,
        ) as get_forecast:
            status, result = self.post_json(
                "/api/weather",
                {"location": "Jackson, Tennessee", "consent": True},
            )
        self.assertEqual(status, 200)
        self.assertEqual(result, forecast)
        get_forecast.assert_called_once_with("Jackson, Tennessee")
        self.assertEqual(web_app._conversation.calls, [])

    def test_weather_api_returns_candidates_for_ambiguous_place(self):
        with patch.object(
            web_app._weather,
            "get_forecast",
            side_effect=AmbiguousWeatherLocation(
                ["Jackson, Tennessee", "Jackson, Mississippi"]
            ),
        ):
            request = Request(
                self.base_url + "/api/weather",
                data=json.dumps(
                    {"location": "Jackson", "consent": True}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 409)
        body = json.loads(error.exception.read().decode("utf-8"))
        self.assertEqual(
            body["candidates"],
            ["Jackson, Tennessee", "Jackson, Mississippi"],
        )

    def test_edith_scan_requires_explicit_confirmation(self):
        with patch.object(web_app._workspace, "read_file") as read_file:
            request = Request(
                self.base_url + "/api/security/scan",
                data=json.dumps(
                    {"path": "src/example.py", "confirm": False}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)
        read_file.assert_not_called()

    def test_edith_scan_is_read_only_and_redacts_detected_secret(self):
        secret = "local-secret-value-123"
        selected_file = self.workspace_root / "src" / "security.py"
        selected_file.write_text(
            f'API_KEY = "{secret}"\nresult = eval(user_input)\n',
            encoding="utf-8",
        )
        status, result = self.post_json(
            "/api/security/scan",
            {"path": "src/security.py", "confirm": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [finding["rule"] for finding in result["findings"]],
            ["SEC001", "PY001"],
        )
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("not proof of safety", result["disclaimer"])
        self.assertEqual(
            selected_file.read_text(encoding="utf-8"),
            f'API_KEY = "{secret}"\nresult = eval(user_input)\n',
        )
        self.assertEqual(web_app._conversation.calls, [])

    def test_ultron_review_api_returns_report_without_using_chat_history(self):
        with patch.object(
            web_app._ultron_reviewer,
            "review",
            return_value="Verdict: revise.",
        ) as review:
            status, result = self.post_json(
                "/api/ultron/review",
                {"text": "A plan to launch a small shop."},
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["review"], "Verdict: revise.")
        review.assert_called_once_with("A plan to launch a small shop.")
        self.assertEqual(web_app._conversation.calls, [])

    def test_ultron_review_api_rejects_blank_text(self):
        request = Request(
            self.base_url + "/api/ultron/review",
            data=json.dumps({"text": "  "}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)

        self.assertEqual(error.exception.code, 400)
        self.assertIn("Paste a plan or draft", error.exception.read().decode("utf-8"))

    def test_chat_api_automatically_routes_clear_specialist_requests(self):
        status, result = self.post_json(
            "/api/chat",
            {"message": "Can you check the security of this login code?"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["agent"], "EDITH")
        self.assertEqual(result["agent_id"], "edith")
        self.assertEqual(result["routing"], "automatic")
        self.assertEqual(
            web_app._conversation.calls,
            [("Can you check the security of this login code?", "edith")],
        )

    def test_chat_task_records_input_route_and_completion(self):
        _status, response = self.post_json(
            "/api/chat",
            {"message": "What's the forecast tomorrow?"},
        )
        with urlopen(self.base_url + "/api/tasks", timeout=3) as result:
            tasks = json.loads(result.read().decode("utf-8"))["tasks"]

        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["task_id"], response["task_id"])
        self.assertEqual(task["message"], "What's the forecast tomorrow?")
        self.assertEqual(task["agent_id"], "friday")
        self.assertEqual(task["routing"], "automatic")
        self.assertEqual(task["status"], "completed")
        self.assertIsNotNone(task["created_at"])
        self.assertIsNotNone(task["completed_at"])
        self.assertIsNone(task["error"])

    def test_chat_task_records_failure_without_success_response(self):
        with patch.object(
            web_app._conversation,
            "ask",
            side_effect=LocalModelError("The local model failed."),
        ):
            request = Request(
                self.base_url + "/api/chat",
                data=json.dumps({"message": "Hello LYLA"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as failure:
                urlopen(request, timeout=3)
        failure_body = json.loads(failure.exception.read().decode("utf-8"))
        with urlopen(self.base_url + "/api/tasks", timeout=3) as result:
            tasks = json.loads(result.read().decode("utf-8"))["tasks"]

        self.assertEqual(failure.exception.code, 503)
        self.assertEqual(failure_body["task_status"], "failed")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], failure_body["task_id"])
        self.assertEqual(tasks[0]["status"], "failed")
        self.assertEqual(tasks[0]["error"], "The local model failed.")
        self.assertIsNotNone(tasks[0]["completed_at"])

    def test_task_history_is_empty_before_chat(self):
        with urlopen(self.base_url + "/api/tasks", timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(result, {"tasks": []})

    def test_chat_api_rejects_unknown_specialist_mode(self):
        request = Request(
            self.base_url + "/api/chat",
            data=b'{"message":"Hi","agent_id":"unknown"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(web_app._conversation.calls, [])

    def test_status_reports_whether_model_is_loaded(self):
        with patch.object(web_app, "is_model_loaded", return_value=True):
            with urlopen(self.base_url + "/api/status", timeout=3) as response:
                result = json.loads(response.read().decode("utf-8"))
        self.assertTrue(result["model_loaded"])

    def test_focus_is_session_local(self):
        status, result = self.post_json(
            "/api/focus",
            {"focus": "Finish the dashboard"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result, {"focus": "Finish the dashboard"})
        self.assertEqual(web_app._mind.focus, "Finish the dashboard")

    def test_settings_round_trip(self):
        status, _result = self.post_json(
            "/api/settings",
            {"voicebox_profile": "LYLA", "voicebox_app": "C:\\Apps\\Voicebox.exe"},
        )
        self.assertEqual(status, 200)
        with urlopen(self.base_url + "/api/settings", timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(result["voicebox_profile"], "LYLA")

    def test_rejects_untrusted_browser_origin(self):
        request = Request(
            self.base_url + "/api/focus",
            data=b'{"focus":"x"}',
            headers={
                "Content-Type": "application/json",
                "Origin": "https://example.com",
            },
            method="POST",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 403)

    def test_local_browser_actions_require_the_exact_same_origin(self):
        handler = object.__new__(web_app.LylaRequestHandler)
        handler.headers = Message()
        local_host = self.base_url.split("://", 1)[1]
        handler.headers["Host"] = local_host
        handler.headers["Origin"] = "http://127.0.0.1:9999"
        self.assertFalse(handler._is_local_request())

        handler.headers.replace_header("Origin", "http://" + local_host)
        self.assertTrue(handler._is_local_request())

    def test_memory_commands_do_not_call_model(self):
        status, result = self.post_json("/api/chat", {"message": "/remember likes tea"})
        self.assertEqual(status, 200)
        self.assertIn("Saved", result["reply"])
        self.assertEqual(result["task_status"], "completed")
        self.assertEqual(result["agent_id"], "lyla")
        self.assertEqual(result["routing"], "command")
        self.assertEqual(web_app._conversation.calls, [])
        with urlopen(self.base_url + "/api/tasks", timeout=3) as response:
            tasks = json.loads(response.read().decode("utf-8"))["tasks"]
        self.assertEqual(tasks[0]["status"], "completed")
        self.assertEqual(tasks[0]["message"], "/remember likes tea")
        self.assertEqual(tasks[0]["agent_id"], "lyla")
        self.assertEqual(tasks[0]["routing"], "command")


if __name__ == "__main__":
    unittest.main()
