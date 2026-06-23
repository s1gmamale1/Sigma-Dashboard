"""Unit tests for the SigmaControl JSON-RPC unix-socket client.

Uses an injected fake transport — no real socket, no real token. Verifies the
auth handshake, the double-nested tools.invoke unwrap, and that malformed /
truncated / rejected responses raise cleanly instead of crashing.
"""

import json

import pytest

from backend.app.hq.adapters.control_socket import (
    ControlSocketClient,
    ControlSocketError,
)


class FakeTransport:
    """Replays canned JSON-RPC response lines; records what was sent."""

    def __init__(self, responses, *, fail_connect=False):
        self._responses = list(responses)
        self.sent: list[str] = []
        self.closed = False
        self._connected = False
        self._fail_connect = fail_connect

    def connect(self):
        if self._fail_connect:
            raise OSError("connection refused")
        self._connected = True

    def send_line(self, line: str) -> None:
        self.sent.append(line)

    def read_line(self) -> str:
        return self._responses.pop(0) if self._responses else ""

    def close(self) -> None:
        self.closed = True


def _line(obj) -> str:
    return json.dumps(obj) + "\n"


HELLO_OK = _line({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})


def _client(responses, **kw):
    t = FakeTransport(responses)
    c = ControlSocketClient(lambda: t, token="secret-token-value", label="sigma-hq", **kw)
    return c, t


def test_hello_handshake_succeeds_and_sends_token() -> None:
    c, t = _client([HELLO_OK])
    with c:
        pass
    # hello was sent with the token + label
    hello_req = json.loads(t.sent[0])
    assert hello_req["method"] == "control.hello"
    assert hello_req["params"]["token"] == "secret-token-value"
    assert hello_req["params"]["label"] == "sigma-hq"
    assert t.closed is True  # transport closed on exit


def test_hello_rejected_raises() -> None:
    c, _ = _client([_line({"jsonrpc": "2.0", "id": 1, "result": {"ok": False}})])
    with pytest.raises(ControlSocketError):
        with c:
            pass


def test_connect_failure_raises_control_socket_error() -> None:
    t = FakeTransport([], fail_connect=True)
    c = ControlSocketClient(lambda: t, token="t", label="l")
    with pytest.raises(ControlSocketError):
        with c:
            pass


def test_invoke_unwraps_double_nested_result() -> None:
    payload = {"workspaces": [{"id": "w1", "name": "A"}]}
    c, t = _client([HELLO_OK, _line({"jsonrpc": "2.0", "id": 2, "result": {"ok": True, "result": payload}})])
    with c:
        got = c.invoke("list_workspaces")
    assert got == payload
    inv = json.loads(t.sent[1])
    assert inv["method"] == "tools.invoke"
    assert inv["params"] == {"name": "list_workspaces", "args": {}}


def test_invoke_tool_error_raises() -> None:
    c, _ = _client([HELLO_OK, _line({"jsonrpc": "2.0", "id": 2, "result": {"ok": False, "error": "boom"}})])
    with pytest.raises(ControlSocketError):
        with c:
            c.invoke("list_workspaces")


def test_malformed_json_raises() -> None:
    c, _ = _client([HELLO_OK, "{ this is not json\n"])
    with pytest.raises(ControlSocketError):
        with c:
            c.invoke("list_workspaces")


def test_truncated_eof_raises() -> None:
    c, _ = _client([HELLO_OK, ""])  # server closed mid-stream
    with pytest.raises(ControlSocketError):
        with c:
            c.invoke("list_workspaces")


def test_token_not_in_repr() -> None:
    c, _ = _client([HELLO_OK])
    assert "secret-token-value" not in repr(c)
