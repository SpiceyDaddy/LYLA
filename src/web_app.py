import json
import logging
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.agents import get_agent, get_agent_summaries, route_agent_id
from src.conversation_manager import ConversationManager
from src.defensive_scanner import DefensiveFileScanner
from src.lyla_core.text_pipeline import LocalModelError, is_model_loaded
from src.memory import (
    MindMemory,
    SoulMemory,
    handle_memory_command,
    is_memory_command,
)
from src.task_tracker import ChatTask, ChatTaskTracker
from src.voicebox_client import VoiceboxClient, VoiceboxError
from src.weather_client import (
    AmbiguousWeatherLocation,
    OpenMeteoClient,
    WeatherServiceError,
)
from src.workspace_tools import WorkspaceAssistant
from src.ultron_reviewer import UltronReviewer

HOST = "127.0.0.1"
PORT = 8765
DASHBOARD_PATH = Path(__file__).parent / "web" / "dashboard.html"
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = Path.home() / ".lyla-ai" / "desktop.json"
MAX_REQUEST_BYTES = 64 * 1024
MAX_WORKSPACE_REQUEST_BYTES = 6_400_000
logger = logging.getLogger(__name__)

_soul = None
_mind = None
_conversation = None
_task_tracker = ChatTaskTracker()
_workspace = WorkspaceAssistant(WORKSPACE_ROOT)
_weather = OpenMeteoClient()
_edith_scanner = DefensiveFileScanner()
_ultron_reviewer = UltronReviewer()
_settings_lock = threading.Lock()
_settings_lock = threading.Lock()


def initialize_app_state() -> None:
    global _soul, _mind, _conversation
    if _conversation is not None:
        return
    _soul = SoulMemory()
    _mind = MindMemory()
    _mind.focus = "Keep it simple. One thing at a time."
    _conversation = ConversationManager(soul=_soul, mind=_mind)


def load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        return {"voicebox_profile": "", "voicebox_app": ""}
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read LYLA settings: {exc}") from exc
    return {
        "voicebox_profile": str(settings.get("voicebox_profile", "")),
        "voicebox_app": str(settings.get("voicebox_app", "")),
    }


def save_settings(settings: dict[str, str]) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
    except OSError as exc:
        raise RuntimeError(f"Could not save LYLA settings: {exc}") from exc


def open_voicebox(configured_path: str) -> str:
    candidates = [Path(configured_path).expanduser()] if configured_path.strip() else []
    for folder_name in ("APPDATA", "PROGRAMDATA"):
        root = os.environ.get(folder_name)
        if not root:
            continue
        shortcuts = (
            Path(root)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
        if shortcuts.is_dir():
            candidates.extend(shortcuts.glob("**/*Voicebox*.lnk"))
            candidates.extend(shortcuts.glob("**/*Voicebox*.exe"))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            os.startfile(str(candidate))
        except OSError as exc:
            raise RuntimeError(f"Could not open Voicebox at {candidate}: {exc}") from exc
        return "Opened Voicebox."

    webbrowser.open("https://github.com/jamiepine/voicebox/releases/latest")
    return (
        "Voicebox was not found. Opened the release page; install Voicebox, "
        "then set its application path in LYLA settings."
    )


class LylaRequestHandler(BaseHTTPRequestHandler):
    server_version = "LYLA-local/1.0"

    def log_message(self, _format: str, *_args) -> None:
        logger.debug("Local dashboard request")

    def _is_local_request(self) -> bool:
        host_header = self.headers.get("Host", "").lower()
        try:
            host = urlsplit(f"//{host_header}").hostname or ""
        except ValueError:
            return False
        origin = self.headers.get("Origin")
        allowed_hosts = {"127.0.0.1", "localhost", "::1"}
        if host not in allowed_hosts:
            return False
        if origin is None:
            return True
        try:
            parsed_origin = urlsplit(origin)
        except ValueError:
            return False
        return (
            parsed_origin.scheme == "http"
            and parsed_origin.hostname in allowed_hosts
            and parsed_origin.netloc.lower() == host_header
        )

    def _send_json(self, status: HTTPStatus, data: dict) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(
        self,
        status: HTTPStatus,
        message: str,
        task: ChatTask | None = None,
    ) -> None:
        result = {"error": message}
        if task is not None:
            result.update(
                {
                    "task_id": task.task_id,
                    "task_status": task.status,
                    "agent": task.agent_id.upper(),
                }
            )
        self._send_json(status, result)

    def _read_json(self, max_bytes: int = MAX_REQUEST_BYTES) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length < 1 or content_length > max_bytes:
            raise ValueError("Request body is missing or exceeds the size limit.")
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")
        return payload

    def do_GET(self) -> None:
        if not self._is_local_request():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Local requests only."})
            return
        route = urlsplit(self.path).path
        if route == "/api/workspace/read":
            try:
                query = parse_qs(
                    urlsplit(self.path).query,
                    strict_parsing=True,
                    max_num_fields=1,
                )
            except ValueError:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Provide one workspace-relative path."},
                )
                return
            paths = query.get("path", [])
            if len(paths) != 1:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Provide one workspace-relative path."},
                )
                return
            try:
                result = _workspace.read_file(paths[0])
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)}
                )
                return
            self._send_json(HTTPStatus.OK, result)
            return

        if route in {"/", "/dashboard.html"}:
            try:
                page = DASHBOARD_PATH.read_bytes()
            except OSError as exc:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"Could not load LYLA dashboard: {exc}"},
                )
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(page)
            return

        if route == "/api/status":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "online",
                    "model_loaded": is_model_loaded(),
                    "focus": _mind.focus,
                },
            )
            return

        if route == "/api/agents":
            self._send_json(HTTPStatus.OK, {"agents": get_agent_summaries()})
            return

        if route == "/api/tasks":
            self._send_json(
                HTTPStatus.OK,
                {"tasks": _task_tracker.recent()},
            )
            return

        if route == "/api/settings":
            try:
                with _settings_lock:
                    self._send_json(HTTPStatus.OK, load_settings())
            except RuntimeError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._is_local_request():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Local requests only."})
            return
        task_record = None
        try:
            route = urlsplit(self.path).path
            payload = self._read_json(
                MAX_WORKSPACE_REQUEST_BYTES
                if route == "/api/workspace/preview"
                else MAX_REQUEST_BYTES
            )

            if route == "/api/chat":
                message = payload.get("message")
                agent_id = payload.get("agent_id", "auto")
                if not isinstance(message, str) or not message.strip():
                    raise ValueError("Enter a message before sending.")
                if not isinstance(agent_id, str):
                    raise ValueError("Agent selection must be text.")
                automatic_routing = agent_id == "auto"
                memory_command = is_memory_command(message)
                if memory_command:
                    agent_id = "lyla"
                elif automatic_routing:
                    agent_id = route_agent_id(message.strip())
                selected_agent = get_agent(agent_id)
                routing_type = (
                    "command"
                    if memory_command
                    else "automatic"
                    if automatic_routing
                    else "manual"
                )
                task_record = _task_tracker.start(
                    message.strip(),
                    selected_agent.id,
                    routing_type,
                )
                try:
                    command_response = handle_memory_command(message, _soul, _mind)
                    if command_response is not None:
                        _task_tracker.complete(task_record.task_id)
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "reply": command_response,
                                "agent": "LYLA",
                                "agent_id": "lyla",
                                "routing": "command",
                                "task_id": task_record.task_id,
                                "task_status": task_record.status,
                            },
                        )
                        return
                    reply, _ = _conversation.ask(message.strip(), agent_id=agent_id)
                    _task_tracker.complete(task_record.task_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "reply": reply,
                            "agent": selected_agent.name,
                            "agent_id": selected_agent.id,
                            "routing": routing_type,
                            "task_id": task_record.task_id,
                            "task_status": task_record.status,
                        },
                    )
                except Exception as exc:
                    if task_record.status == "in_progress":
                        _task_tracker.fail(task_record.task_id, str(exc))
                    raise
                return

            if route == "/api/workspace/preview":
                path = payload.get("path")
                content = payload.get("content")
                if not isinstance(path, str) or not isinstance(content, str):
                    raise ValueError("File path and content must be text.")
                self._send_json(
                    HTTPStatus.OK,
                    _workspace.preview_change(path, content),
                )
                return

            if route == "/api/workspace/apply":
                approval_token = payload.get("approval_token")
                if not isinstance(approval_token, str):
                    raise ValueError("A change approval is required.")
                self._send_json(
                    HTTPStatus.OK,
                    _workspace.apply_change(approval_token),
                )
                return

            if route == "/api/workspace/tests":
                if payload.get("confirm") is not True:
                    raise ValueError(
                        "Confirm that you want to execute this workspace's tests."
                    )
                self._send_json(HTTPStatus.OK, _workspace.run_tests())
                return

            if route == "/api/weather":
                if payload.get("consent") is not True:
                    raise ValueError(
                        "Confirm before sending the place name to Open-Meteo."
                    )
                location = payload.get("location")
                if not isinstance(location, str):
                    raise ValueError("Enter a place name.")
                try:
                    result = _weather.get_forecast(location)
                except AmbiguousWeatherLocation as exc:
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {
                            "error": str(exc),
                            "candidates": exc.candidates,
                        },
                    )
                    return
                except WeatherServiceError as exc:
                    self._send_json(
                        HTTPStatus.BAD_GATEWAY,
                        {"error": str(exc)},
                    )
                    return
                self._send_json(HTTPStatus.OK, result)
                return

            if route == "/api/security/scan":
                if payload.get("confirm") is not True:
                    raise ValueError(
                        "Confirm the read-only scan of the selected file."
                    )
                path = payload.get("path")
                if not isinstance(path, str):
                    raise ValueError("Choose one workspace-relative file.")
                selected_file = _workspace.read_file(path)
                result = _edith_scanner.scan(
                    selected_file["path"],
                    selected_file["content"],
                )
                self._send_json(HTTPStatus.OK, result)
                return

            if route == "/api/ultron/review":
                text = payload.get("text")
                if not isinstance(text, str):
                    raise ValueError("Review text must be text.")
                self._send_json(
                    HTTPStatus.OK,
                    {"review": _ultron_reviewer.review(text)},
                )
                return

            if route == "/api/focus":
                focus = payload.get("focus", "")
                if not isinstance(focus, str):
                    raise ValueError("Focus must be text.")
                _mind.focus = focus.strip()
                self._send_json(HTTPStatus.OK, {"focus": _mind.focus})
                return

            if route == "/api/speak":
                text = payload.get("text")
                profile = payload.get("profile", "")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("There is no text to speak.")
                if not isinstance(profile, str):
                    raise ValueError("Voicebox profile must be text.")
                settings = load_settings()
                selected_profile = profile.strip() or settings["voicebox_profile"]
                result = VoiceboxClient(profile=selected_profile).speak(text)
                self._send_json(HTTPStatus.OK, {"status": "completed", "message": result})
                return

            if route == "/api/settings":
                profile = payload.get("voicebox_profile", "")
                app_path = payload.get("voicebox_app", "")
                if not isinstance(profile, str) or not isinstance(app_path, str):
                    raise ValueError("Voice settings must be text.")
                with _settings_lock:
                    save_settings(
                        {
                            "voicebox_profile": profile.strip(),
                            "voicebox_app": app_path.strip(),
                        }
                    )
                self._send_json(HTTPStatus.OK, {"status": "saved"})
                return

            if route == "/api/open-voicebox":
                settings = load_settings()
                result = open_voicebox(settings["voicebox_app"])
                self._send_json(HTTPStatus.OK, {"message": result})
                return

            if route == "/api/voicebox-check":
                settings = load_settings()
                VoiceboxClient(
                    profile=settings["voicebox_profile"]
                ).check_connection()
                self._send_json(HTTPStatus.OK, {"status": "connected"})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except (ValueError, VoiceboxError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc), task_record)
        except LocalModelError as exc:
            self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc), task_record)
        except (RuntimeError, OSError) as exc:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), task_record
            )
        except Exception as exc:
            logger.exception("Unexpected LYLA local API error")
            if task_record is not None and task_record.status == "in_progress":
                _task_tracker.fail(task_record.task_id, str(exc))
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "LYLA encountered an unexpected local error.",
                task_record,
            )


class LocalLylaServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    initialize_app_state()
    try:
        server = LocalLylaServer((HOST, PORT), LylaRequestHandler)
    except OSError as exc:
        raise RuntimeError(
            f"Could not start LYLA dashboard on http://{HOST}:{PORT}: {exc}"
        ) from exc
    url = f"http://{HOST}:{PORT}/"
    print(f"LYLA dashboard is running at {url}")
    print("Close this window to stop LYLA.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LYLA dashboard.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
