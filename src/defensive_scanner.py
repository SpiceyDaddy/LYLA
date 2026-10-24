from datetime import datetime, timezone
from pathlib import Path
import re


MAX_SCANNED_FILE_CHARACTERS = 1_048_576
MAX_FINDINGS = 200

_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:api[_-]?key|client[_-]?secret|secret(?:[_-]?key)?|password|"
    r"passwd|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*"
    r"(['\"])([^'\"\r\n]{8,})\1",
    re.IGNORECASE,
)
_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    re.IGNORECASE,
)
_TOKEN_SHAPE = re.compile(r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,})\b")
_PLACEHOLDER_VALUES = (
    "example",
    "changeme",
    "change_me",
    "placeholder",
    "your_",
    "replace_me",
    "dummy",
    "test_",
)
_PYTHON_RULES = (
    (
        "PY001",
        "MEDIUM",
        re.compile(r"\b(?:eval|exec)\s*\("),
        "Dynamic code evaluation found.",
        "Avoid evaluating constructed strings; use an explicit parser or allowlisted operation.",
    ),
    (
        "PY002",
        "MEDIUM",
        re.compile(
            r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\(.*"
            r"\bshell\s*=\s*True\b"
        ),
        "A subprocess call enables shell parsing on this line.",
        "Prefer an argument list with shell disabled, and validate inputs at the boundary.",
    ),
    (
        "PY003",
        "HIGH",
        re.compile(r"\bpickle\.(?:load|loads)\s*\("),
        "Pickle deserialization can execute code when the input is untrusted.",
        "Do not load untrusted pickle data; use a data-only format and validate its schema.",
    ),
    (
        "PY004",
        "MEDIUM",
        re.compile(r"\byaml\.load\s*\("),
        "A YAML loader call needs review for unsafe loader configuration.",
        "Use a safe loader for untrusted YAML and validate the resulting data.",
    ),
    (
        "PY005",
        "MEDIUM",
        re.compile(r"\btempfile\.mktemp\s*\("),
        "The insecure temporary-name helper is used.",
        "Use a secure temporary-file API such as NamedTemporaryFile.",
    ),
    (
        "PY006",
        "LOW",
        re.compile(r"\bhashlib\.(?:md5|sha1)\s*\(", re.IGNORECASE),
        "A legacy hash function is used.",
        "Use a modern hash for integrity checks; use a password-hashing function for passwords.",
    ),
)


class DefensiveFileScanner:
    """Run bounded, read-only heuristic checks on explicitly supplied text."""

    def scan(self, relative_path: str, content: str) -> dict:
        if not isinstance(content, str):
            raise ValueError("Selected file content must be text.")
        if len(content) > MAX_SCANNED_FILE_CHARACTERS:
            raise ValueError("Selected files are limited to 1 MB of text.")

        findings = []
        is_python = Path(relative_path).suffix.casefold() in {".py", ".pyi"}
        for line_number, line in enumerate(content.splitlines(), start=1):
            self._check_secrets(line, line_number, findings)
            if is_python and not line.lstrip().startswith("#"):
                self._check_python(line, line_number, findings)

        total = len(findings)
        shown = findings[:MAX_FINDINGS]
        severities = {
            severity: sum(
                finding["severity"] == severity for finding in findings
            )
            for severity in ("HIGH", "MEDIUM", "LOW")
        }
        return {
            "path": relative_path,
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "findings": shown,
            "summary": {
                "total": total,
                "shown": len(shown),
                "truncated": total > MAX_FINDINGS,
                "by_severity": severities,
            },
            "disclaimer": (
                "Heuristic, read-only checks only. Findings may be false "
                "positives; no finding is not proof of safety."
            ),
        }

    @staticmethod
    def _check_secrets(line: str, line_number: int, findings: list[dict]) -> None:
        assignment = _SECRET_ASSIGNMENT.search(line)
        if assignment:
            value = assignment.group(2).strip().casefold()
            if value and not any(
                value == placeholder or value.startswith(placeholder)
                for placeholder in _PLACEHOLDER_VALUES
            ):
                findings.append(
                    {
                        "rule": "SEC001",
                        "severity": "HIGH",
                        "line": line_number,
                        "message": "Potential hard-coded credential detected; value redacted.",
                        "recommendation": (
                            "Remove the credential, rotate it if it was real, "
                            "and load secrets from a secure local configuration."
                        ),
                    }
                )
        if _PRIVATE_KEY_HEADER.search(line):
            findings.append(
                {
                    "rule": "SEC002",
                    "severity": "HIGH",
                    "line": line_number,
                    "message": "A private-key header was found; key contents are not displayed.",
                    "recommendation": (
                        "Keep private keys out of source files and rotate the key "
                        "if it was exposed."
                    ),
                }
            )
        if _TOKEN_SHAPE.search(line):
            findings.append(
                {
                    "rule": "SEC003",
                    "severity": "HIGH",
                    "line": line_number,
                    "message": "A credential-shaped token was detected; value redacted.",
                    "recommendation": (
                        "Verify whether it is an active credential, remove it "
                        "from source, and rotate it if necessary."
                    ),
                }
            )

    @staticmethod
    def _check_python(line: str, line_number: int, findings: list[dict]) -> None:
        for rule, severity, pattern, message, recommendation in _PYTHON_RULES:
            if pattern.search(line):
                findings.append(
                    {
                        "rule": rule,
                        "severity": severity,
                        "line": line_number,
                        "message": message,
                        "recommendation": recommendation,
                    }
                )
