"""Read-only JSON-RPC client for SigmaLink/SigmaControl External Control.

The socket is a Unix-domain JSON-RPC line protocol:
1. `control.hello` with a token + client label.
2. `tools.invoke` with `{name, args}`.

This module intentionally keeps the token private: it is only sent on the wire
and never included in repr/error messages.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class ControlSocketError(RuntimeError):
    """Raised when the control socket is unreachable or returns bad data."""


class ControlSocketTransport(Protocol):
    def connect(self) -> None: ...
    def send_line(self, line: str) -> None: ...
    def read_line(self) -> str: ...
    def close(self) -> None: ...


@dataclass
class UnixSocketTransport:
    socket_path: str
    timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        self._sock: socket.socket | None = None
        self._file = None

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_seconds)
        sock.connect(self.socket_path)
        self._sock = sock
        self._file = sock.makefile("rwb", buffering=0)

    def send_line(self, line: str) -> None:
        if self._file is None:
            raise OSError("control socket is not connected")
        self._file.write(line.encode("utf-8"))

    def read_line(self) -> str:
        if self._file is None:
            raise OSError("control socket is not connected")
        raw = self._file.readline()
        return raw.decode("utf-8") if raw else ""

    def close(self) -> None:
        try:
            if self._file is not None:
                self._file.close()
        finally:
            self._file = None
            if self._sock is not None:
                self._sock.close()
                self._sock = None


class ControlSocketClient:
    def __init__(
        self,
        transport_factory: Callable[[], ControlSocketTransport],
        *,
        token: str,
        label: str = "sigma-hq",
    ) -> None:
        self._transport_factory = transport_factory
        self._token = token
        self._label = label
        self._transport: ControlSocketTransport | None = None
        self._next_id = 0

    def __repr__(self) -> str:
        return f"ControlSocketClient(label={self._label!r})"

    def __enter__(self) -> "ControlSocketClient":
        self._transport = self._transport_factory()
        try:
            self._transport.connect()
            hello = self._rpc("control.hello", {"token": self._token, "label": self._label})
        except Exception as exc:  # noqa: BLE001 — normalize transport/protocol failures
            self.close()
            raise ControlSocketError("control socket handshake failed") from exc
        if not isinstance(hello, dict) or hello.get("ok") is not True:
            self.close()
            raise ControlSocketError("control socket handshake rejected")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def invoke(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._rpc("tools.invoke", {"name": name, "args": args or {}})
        if not isinstance(result, dict):
            raise ControlSocketError("control tool returned non-object result")
        if result.get("ok") is not True:
            raise ControlSocketError("control tool invocation failed")
        payload = result.get("result")
        if not isinstance(payload, dict):
            raise ControlSocketError("control tool returned malformed payload")
        return payload

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        if self._transport is None:
            raise ControlSocketError("control socket is not connected")
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        try:
            self._transport.send_line(json.dumps(msg, separators=(",", ":")) + "\n")
            line = self._transport.read_line()
        except Exception as exc:  # noqa: BLE001
            raise ControlSocketError("control socket I/O failed") from exc
        if not line:
            raise ControlSocketError("control socket closed unexpectedly")
        try:
            reply = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ControlSocketError("control socket returned malformed JSON") from exc
        if not isinstance(reply, dict):
            raise ControlSocketError("control socket returned non-object JSON")
        if "error" in reply:
            raise ControlSocketError("control socket JSON-RPC error")
        return reply.get("result")


def make_control_socket_client(
    socket_path: str,
    token: str,
    *,
    label: str = "sigma-hq",
    timeout_seconds: float = 2.0,
) -> ControlSocketClient:
    return ControlSocketClient(
        lambda: UnixSocketTransport(socket_path, timeout_seconds=timeout_seconds),
        token=token,
        label=label,
    )
