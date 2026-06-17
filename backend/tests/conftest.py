import pytest

from backend.app.main import app


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """The FastAPI `app` is a module-level singleton shared by every test. Some tests
    install `app.dependency_overrides` (e.g. to stub auth or the DB session); clear
    them after each test so overrides never leak across files and silently disable
    auth enforcement in a later test."""
    yield
    app.dependency_overrides.clear()
