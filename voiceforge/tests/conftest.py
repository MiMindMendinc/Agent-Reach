"""Shared fixtures: a fake engine so the API can be tested without the model.

Imports of VoiceForge's dependencies happen inside the fixtures. Pytest can
load this file even when ../conftest.py skips these tests because the
dependencies are not installed, and it must not fail in that case.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def fake_engine() -> Any:
    from voiceforge_fakes import FakeEngine

    return FakeEngine()


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., Any]]:
    """Build a TestClient for an app with the given engine and settings."""
    from fastapi.testclient import TestClient
    from server import Settings, create_app
    from voiceforge_fakes import FakeEngine

    clients: list[TestClient] = []

    def build(engine: Any = None, **settings_overrides: Any) -> TestClient:
        settings = Settings(model_dir=tmp_path / "models", **settings_overrides)
        app = create_app(settings, engine if engine is not None else FakeEngine())
        client = TestClient(app, base_url="http://localhost")
        client.__enter__()  # runs the app's startup (lifespan)
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[..., Any], fake_engine: Any) -> Any:
    return make_client(fake_engine)
