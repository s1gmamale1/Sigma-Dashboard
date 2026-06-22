"""Credential resolution for the SigmaControl socket.

Verifies shell-compatible parsing (``shlex``) of the hermes credentials file —
the socket path contains a space ("Application Support") and is single-quoted,
and a *commented* stale ``external-control.sock`` line must be ignored. No real
token anywhere; the token must never appear in repr.
"""

from types import SimpleNamespace

from backend.app.hq.adapters.control_creds import (
    parse_env_file,
    resolve_control_creds,
)

CREDS = """\
# Hermes external control credentials
# SIGMA_CONTROL_SOCKET='/Users/x/Library/Application Support/SigmaLink/external-control.sock'  # STALE
SIGMA_CONTROL_SOCKET='/Users/x/Library/Application Support/SigmaLink/control.sock'
SIGMA_CONTROL_TOKEN=tok_abc123
export SIGMA_CONTROL_LABEL="sigma-hq-live"
"""


def _settings(creds_path, sock=None):
    return SimpleNamespace(hq_control_creds_path=creds_path, hq_sigmalink_socket=sock)


def test_parse_handles_quotes_spaces_and_comments() -> None:
    vals = parse_env_file(CREDS)
    assert vals["SIGMA_CONTROL_SOCKET"] == "/Users/x/Library/Application Support/SigmaLink/control.sock"
    assert vals["SIGMA_CONTROL_TOKEN"] == "tok_abc123"
    assert vals["SIGMA_CONTROL_LABEL"] == "sigma-hq-live"
    # the commented stale path must not win
    assert "external-control" not in vals["SIGMA_CONTROL_SOCKET"]


def test_parse_handles_unquoted_value_with_space() -> None:
    vals = parse_env_file("SIGMA_CONTROL_SOCKET=/a b/c.sock\n")
    assert vals["SIGMA_CONTROL_SOCKET"] == "/a b/c.sock"


def test_resolve_from_file(tmp_path, monkeypatch) -> None:
    for k in ("SIGMA_CONTROL_SOCKET", "SIGMA_CONTROL_TOKEN", "SIGMA_CONTROL_LABEL"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".credentials"
    p.write_text(CREDS)
    creds = resolve_control_creds(_settings(str(p)))
    assert creds is not None
    assert creds.socket_path.endswith("/SigmaLink/control.sock")
    assert " " in creds.socket_path  # the space survived
    assert creds.token == "tok_abc123"
    assert creds.label == "sigma-hq-live"


def test_env_overrides_file(tmp_path, monkeypatch) -> None:
    p = tmp_path / ".credentials"
    p.write_text(CREDS)
    monkeypatch.setenv("SIGMA_CONTROL_SOCKET", "/env/override.sock")
    monkeypatch.setenv("SIGMA_CONTROL_TOKEN", "env_tok")
    monkeypatch.delenv("SIGMA_CONTROL_LABEL", raising=False)
    creds = resolve_control_creds(_settings(str(p)))
    assert creds.socket_path == "/env/override.sock"
    assert creds.token == "env_tok"


def test_explicit_setting_overrides_env_and_file(tmp_path, monkeypatch) -> None:
    p = tmp_path / ".credentials"
    p.write_text(CREDS)
    monkeypatch.setenv("SIGMA_CONTROL_SOCKET", "/env/override.sock")
    creds = resolve_control_creds(_settings(str(p), sock="/explicit/hq.sock"))
    assert creds.socket_path == "/explicit/hq.sock"


def test_missing_token_returns_none(tmp_path, monkeypatch) -> None:
    for k in ("SIGMA_CONTROL_SOCKET", "SIGMA_CONTROL_TOKEN", "SIGMA_CONTROL_LABEL"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".credentials"
    p.write_text("SIGMA_CONTROL_SOCKET='/a/b.sock'\n")  # no token
    assert resolve_control_creds(_settings(str(p))) is None


def test_missing_file_and_env_returns_none(tmp_path, monkeypatch) -> None:
    for k in ("SIGMA_CONTROL_SOCKET", "SIGMA_CONTROL_TOKEN", "SIGMA_CONTROL_LABEL"):
        monkeypatch.delenv(k, raising=False)
    assert resolve_control_creds(_settings(str(tmp_path / "nope"))) is None


def test_resolve_expands_tilde_path(tmp_path, monkeypatch) -> None:
    for k in ("SIGMA_CONTROL_SOCKET", "SIGMA_CONTROL_TOKEN", "SIGMA_CONTROL_LABEL"):
        monkeypatch.delenv(k, raising=False)
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    (home / ".hermes" / ".credentials").write_text(CREDS)
    monkeypatch.setenv("HOME", str(home))
    creds = resolve_control_creds(_settings("~/.hermes/.credentials"))
    assert creds is not None
    assert creds.socket_path.endswith("/SigmaLink/control.sock")


def test_token_not_in_repr(tmp_path, monkeypatch) -> None:
    for k in ("SIGMA_CONTROL_SOCKET", "SIGMA_CONTROL_TOKEN", "SIGMA_CONTROL_LABEL"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".credentials"
    p.write_text(CREDS)
    creds = resolve_control_creds(_settings(str(p)))
    assert "tok_abc123" not in repr(creds)
