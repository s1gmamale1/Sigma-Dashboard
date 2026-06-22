"""Credential resolution for read-only SigmaControl/SigmaLink socket access.

The Hermes credentials file is shell-ish (`export KEY='value with spaces'`) and
may contain stale commented examples. Parse it with comment awareness and
shell-compatible quote handling; never expose tokens in repr.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ControlCreds:
    socket_path: str
    token: str
    label: str = "sigma-hq"

    def __repr__(self) -> str:
        return f"ControlCreds(socket_path={self.socket_path!r}, label={self.label!r}, token=<redacted>)"


def parse_env_file(text: str) -> dict[str, str]:
    vals: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _parse_value(raw_value.strip())
        vals[key] = value
    return vals


def _parse_value(raw: str) -> str:
    if not raw:
        return ""
    try:
        parts = shlex.split(raw, comments=True, posix=True)
    except ValueError:
        return raw.split("#", 1)[0].strip().strip("'\"")
    if parts:
        return " ".join(parts)
    return ""


def resolve_control_creds(settings: Any) -> ControlCreds | None:
    file_vals: dict[str, str] = {}
    path = getattr(settings, "hq_control_creds_path", None)
    if path:
        try:
            file_vals = parse_env_file(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
            file_vals = {}

    socket_path = (
        getattr(settings, "hq_sigmalink_socket", None)
        or os.getenv("SIGMA_CONTROL_SOCKET")
        or file_vals.get("SIGMA_CONTROL_SOCKET")
    )
    token = (
        getattr(settings, "hq_sigmalink_token", None)
        or os.getenv("SIGMA_CONTROL_TOKEN")
        or file_vals.get("SIGMA_CONTROL_TOKEN")
    )
    label = (
        getattr(settings, "hq_sigmalink_label", None)
        or os.getenv("SIGMA_CONTROL_LABEL")
        or file_vals.get("SIGMA_CONTROL_LABEL")
        or "sigma-hq"
    )
    if not socket_path or not token:
        return None
    return ControlCreds(socket_path=str(socket_path), token=str(token), label=str(label))
