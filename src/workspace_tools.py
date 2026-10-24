from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading


MAX_WORKSPACE_FILE_BYTES = 1_048_576
MAX_DIFF_CHARACTERS = 64_000
MAX_TEST_OUTPUT_CHARACTERS = 24_000
MAX_PENDING_APPROVALS = 32
APPROVAL_LIFETIME = timedelta(minutes=5)
TEST_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class PendingChange:
    path: str
    content: bytes
    original_hash: str | None
    expires_at: datetime


class WorkspaceAssistant:
    """Provide explicit, workspace-scoped file changes and test execution."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self._pending: dict[str, PendingChange] = {}
        self._lock = threading.Lock()

    def read_file(self, relative_path: str) -> dict[str, str]:
        target = self._resolve_file(relative_path, allow_missing=False)
        content = self._read_bytes(target)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text files can be read.") from exc
        return {
            "path": target.relative_to(self.workspace_root).as_posix(),
            "content": self._normalize_newlines(text),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def preview_change(
        self, relative_path: str, content: str
    ) -> dict[str, str | bool]:
        if not isinstance(content, str):
            raise ValueError("File content must be text.")
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("File content must be valid UTF-8 text.") from exc
        if len(encoded) > MAX_WORKSPACE_FILE_BYTES:
            raise ValueError("File content exceeds the 1 MB limit.")

        target = self._resolve_file(relative_path, allow_missing=True)
        original = self._read_bytes(target) if target.exists() else b""
        try:
            original_text = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text files can be edited.") from exc
        normalized_original = self._normalize_newlines(original_text)
        normalized_content = self._normalize_newlines(content)
        if normalized_original == normalized_content:
            return {
                "path": target.relative_to(self.workspace_root).as_posix(),
                "diff": "",
                "no_change": True,
                "approval_token": "",
            }

        diff = "".join(
            difflib.unified_diff(
                normalized_original.splitlines(keepends=True),
                normalized_content.splitlines(keepends=True),
                fromfile=f"a/{target.relative_to(self.workspace_root).as_posix()}",
                tofile=f"b/{target.relative_to(self.workspace_root).as_posix()}",
            )
        )
        if len(diff) > MAX_DIFF_CHARACTERS:
            raise ValueError("The preview is too large to approve safely.")

        token = secrets.token_urlsafe(32)
        newline = self._line_ending(original_text) if original else "\n"
        disk_content = normalized_content.replace("\n", newline).encode("utf-8")
        if len(disk_content) > MAX_WORKSPACE_FILE_BYTES:
            raise ValueError("The edited file would exceed the 1 MB limit.")
        change = PendingChange(
            path=target.relative_to(self.workspace_root).as_posix(),
            content=disk_content,
            original_hash=hashlib.sha256(original).hexdigest()
            if target.exists()
            else None,
            expires_at=datetime.now(timezone.utc) + APPROVAL_LIFETIME,
        )
        with self._lock:
            self._discard_expired()
            if len(self._pending) >= MAX_PENDING_APPROVALS:
                raise ValueError("Too many pending approvals. Wait and preview again.")
            self._pending[token] = change
        return {
            "path": change.path,
            "diff": diff,
            "no_change": False,
            "approval_token": token,
        }

    def apply_change(self, approval_token: str) -> dict[str, str]:
        if not isinstance(approval_token, str) or not approval_token:
            raise ValueError("A valid change approval is required.")
        with self._lock:
            change = self._pending.pop(approval_token, None)
        if change is None or change.expires_at <= datetime.now(timezone.utc):
            raise ValueError("The change approval is missing or expired. Preview it again.")

        target = self._resolve_file(change.path, allow_missing=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".lyla-change-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(change.content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            current = self._read_bytes(target) if target.exists() else None
            current_hash = (
                hashlib.sha256(current).hexdigest() if current is not None else None
            )
            if current_hash != change.original_hash:
                raise ValueError(
                    "The file changed after preview. Load it and preview again."
                )
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

        return {
            "path": change.path,
            "status": "applied",
        }

    def run_tests(self) -> dict[str, int | str | None]:
        tests_directory = self.workspace_root / "tests"
        if not tests_directory.is_dir():
            raise RuntimeError("The workspace has no tests directory.")

        command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = self._timeout_output(exc)
            return {
                "status": "timeout",
                "exit_code": None,
                "output": output[-MAX_TEST_OUTPUT_CHARACTERS:],
            }

        output = (result.stdout + result.stderr).strip()
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "output": output[-MAX_TEST_OUTPUT_CHARACTERS:],
        }

    def _resolve_file(self, relative_path: str, *, allow_missing: bool) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Choose a workspace-relative file path.")
        requested = Path(relative_path.strip())
        reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
        }
        if (
            requested.is_absolute()
            or requested.drive
            or requested.root
            or any(
                part in {"", ".", ".."}
                or ":" in part
                or part.endswith((" ", "."))
                or any(ord(character) < 32 for character in part)
                or part.split(".", 1)[0].rstrip(" .").upper() in reserved_names
                for part in requested.parts
            )
        ):
            raise ValueError("Use a relative path inside the LYLA workspace.")

        candidate = self.workspace_root / requested
        current = self.workspace_root
        for part in requested.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Workspace symlinks are not allowed.")
        if not allow_missing and not candidate.exists():
            raise ValueError("The workspace file does not exist.")

        try:
            resolved = candidate.resolve(strict=not allow_missing)
            resolved.relative_to(self.workspace_root)
        except (OSError, ValueError) as exc:
            raise ValueError("The path must stay inside the LYLA workspace.") from exc
        if resolved == self.workspace_root:
            raise ValueError("Choose a file, not the workspace directory.")
        if allow_missing and not resolved.parent.is_dir():
            raise ValueError("The parent directory must already exist.")
        if resolved.exists() and not resolved.is_file():
            raise ValueError("Only regular files can be read or changed.")
        return resolved

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Could not read workspace file: {exc}") from exc
        if len(content) > MAX_WORKSPACE_FILE_BYTES:
            raise ValueError("Workspace files larger than 1 MB are not supported.")
        return content

    def _discard_expired(self) -> None:
        now = datetime.now(timezone.utc)
        self._pending = {
            token: change
            for token, change in self._pending.items()
            if change.expires_at > now
        }

    @staticmethod
    def _normalize_newlines(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _line_ending(text: str) -> str:
        if "\r\n" in text:
            return "\r\n"
        if "\r" in text:
            return "\r"
        return "\n"

    @staticmethod
    def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
        output = exc.stdout or b""
        error = exc.stderr or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if isinstance(error, bytes):
            error = error.decode("utf-8", errors="replace")
        return f"{output}{error}\nTest run exceeded {TEST_TIMEOUT_SECONDS} seconds."
