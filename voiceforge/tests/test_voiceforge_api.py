"""HTTP API tests. No model files are needed: a fake engine stands in."""

from __future__ import annotations

import asyncio
import io
import threading

import httpx
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from server import MAX_BODY_BYTES, Settings, SettingsError, _hostname, create_app
from tts.engine import MODEL_FILE, VOICES_FILE, SynthesisError, TTSEngine
from voiceforge_fakes import FakeEngine


def error_of(response: httpx.Response) -> str:
    body = response.json()
    assert set(body) == {"error"}, body
    return body["error"]


# --- Missing model ----------------------------------------------------------

def test_starts_and_reports_missing_model(tmp_path):
    engine = TTSEngine(tmp_path / "models")
    app = create_app(Settings(model_dir=tmp_path / "models"), engine)
    with TestClient(app, base_url="http://localhost") as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded"
        assert health["model_loaded"] is False
        assert sorted(health["missing_files"]) == sorted([MODEL_FILE, VOICES_FILE])

        voices = client.get("/voices")
        assert voices.status_code == 503
        assert "download_models.py" in error_of(voices)

        speak = client.post("/speak", json={"text": "Hello"})
        assert speak.status_code == 503
        assert "download_models.py" in error_of(speak)

        assert client.get("/").status_code == 200


# --- Successful speech ------------------------------------------------------

def test_speak_returns_valid_wav(client, fake_engine):
    response = client.post("/speak", json={"text": "Hello there.", "voice": "bf_emma", "speed": 1.25})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    audio, sample_rate = sf.read(io.BytesIO(response.content))
    assert sample_rate == 24000
    assert len(audio) > 0
    assert fake_engine.calls == [("Hello there.", "bf_emma", 1.25)]


def test_speak_uses_default_voice_and_trims_text(client, fake_engine):
    response = client.post("/speak", json={"text": "  Hi  "})
    assert response.status_code == 200
    assert fake_engine.calls == [("Hi", "af_bella", 1.0)]


def test_voices_and_health(client):
    data = client.get("/voices").json()
    assert data["default"] == "af_bella"
    assert {"id": "bm_george", "label": "George (UK, male)", "accent": "UK", "gender": "male"} in data["voices"]
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["model_loaded"] is True


def test_demo_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "VoiceForge" in response.text


# --- Input validation -------------------------------------------------------

@pytest.mark.parametrize(
    ("payload", "status", "message"),
    [
        ({"text": ""}, 400, "Text is required"),
        ({"text": "   \n "}, 400, "Text is required"),
        ({}, 400, "Text is required"),
        ({"text": "... !!"}, 400, "Nothing to speak"),
        ({"text": "x" * 5001}, 400, "too long"),
        ({"text": "hi", "voice": "nobody"}, 400, "Unknown voice 'nobody'"),
        ({"text": "hi", "speed": 3}, 422, "speed"),
        ({"text": "hi", "speed": 0.2}, 422, "speed"),
        ({"text": "hi", "speed": "fast"}, 422, "speed"),
        ({"text": 42}, 422, "text"),
    ],
)
def test_bad_input_is_rejected_cleanly(client, fake_engine, payload, status, message):
    response = client.post("/speak", json=payload)
    assert response.status_code == status
    assert message in error_of(response)
    if status == 400 and "voice" not in payload:
        assert fake_engine.calls == []


def test_max_length_text_is_accepted(client):
    assert client.post("/speak", json={"text": "a" * 5000}).status_code == 200


def test_malformed_json(client):
    response = client.post("/speak", content=b"{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert error_of(response) == "Request body must be valid JSON."


# --- Engine failures --------------------------------------------------------

def test_unexpected_engine_error_does_not_leak_details(make_client):
    client = make_client(FakeEngine(fail_with=RuntimeError("secret internal detail")))
    response = client.post("/speak", json={"text": "Hello"})
    assert response.status_code == 500
    message = error_of(response)
    assert "secret internal detail" not in message
    assert "Traceback" not in response.text
    assert "server log" in message


def test_engine_producing_no_audio_returns_422(make_client):
    client = make_client(FakeEngine(fail_with=SynthesisError("The text produced no audio.")))
    response = client.post("/speak", json={"text": "Hello"})
    assert response.status_code == 422
    assert error_of(response) == "The text produced no audio."


# --- Request size limits ----------------------------------------------------

def test_oversized_body_with_content_length_is_rejected(client, fake_engine):
    body = b'{"text": "' + b"a" * MAX_BODY_BYTES + b'"}'
    response = client.post("/speak", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert "too large" in error_of(response)
    assert fake_engine.calls == []


def test_oversized_chunked_body_is_rejected(client, fake_engine):
    def chunks():
        yield b'{"text": "'
        for _ in range(MAX_BODY_BYTES // 4096 + 2):
            yield b"a" * 4096
        yield b'"}'

    response = client.post("/speak", content=chunks(), headers={"Content-Type": "application/json"})
    assert "content-length" not in {k.lower() for k in response.request.headers}
    assert response.status_code == 413
    assert "too large" in error_of(response)
    assert fake_engine.calls == []


def test_invalid_content_length_is_rejected(client):
    response = client.post(
        "/speak", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": "abc"}
    )
    assert response.status_code == 400


# --- Host and Origin checks -------------------------------------------------

@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000", "LOCALHOST"])
def test_loopback_hosts_are_accepted(client, host):
    assert client.get("/health", headers={"Host": host}).status_code == 200


def test_unknown_host_is_rejected(client):
    # A DNS-rebinding page would reach the server under its own hostname.
    response = client.get("/health", headers={"Host": "attacker.example:8000"})
    assert response.status_code == 400
    assert "VOICEFORGE_ALLOWED_HOSTS" in error_of(response)


def test_wildcard_allowed_hosts(make_client):
    client = make_client(allowed_hosts=frozenset({"*"}))
    assert client.get("/health", headers={"Host": "my-desktop.lan"}).status_code == 200


def test_cross_origin_browser_request_is_rejected(client, fake_engine):
    response = client.post("/speak", json={"text": "Hello"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "VOICEFORGE_ALLOWED_ORIGINS" in error_of(response)
    assert fake_engine.calls == []


def test_same_origin_browser_request_is_accepted(client):
    response = client.post(
        "/speak", json={"text": "Hello"}, headers={"Origin": "http://localhost:8000", "Host": "localhost:8000"}
    )
    assert response.status_code == 200


def test_configured_origin_gets_cors_access(make_client):
    origin = "http://localhost:3000"
    client = make_client(allowed_origins=(origin,))
    preflight = client.options(
        "/speak",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin

    response = client.post("/speak", json={"text": "Hello"}, headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin

    other = client.post("/speak", json={"text": "Hello"}, headers={"Origin": "http://localhost:4000"})
    assert other.status_code == 403


# --- Admission control ------------------------------------------------------

def test_requests_beyond_queue_limit_get_503():
    gate = threading.Event()
    engine = FakeEngine(gate=gate)
    app = create_app(Settings(max_queue=1), engine)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as http:
            first = asyncio.create_task(http.post("/speak", json={"text": "first"}))
            for _ in range(200):
                if engine.calls:
                    break
                await asyncio.sleep(0.01)
            assert engine.calls, "first request never reached the engine"

            busy = await http.post("/speak", json={"text": "second"})
            gate.set()
            done = await first
            return busy, done

    busy, done = asyncio.run(scenario())
    assert busy.status_code == 503
    assert "busy" in error_of(busy)
    assert busy.headers["retry-after"] == "2"
    assert done.status_code == 200
    assert [call[0] for call in engine.calls] == ["first"]


# --- Settings ---------------------------------------------------------------

def test_settings_defaults():
    settings = Settings.from_env({})
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.allowed_hosts == frozenset({"localhost", "127.0.0.1", "::1"})
    assert settings.allowed_origins == ()
    assert settings.max_queue == 4


def test_settings_specific_bind_address_is_allowed_as_host():
    settings = Settings.from_env({"VOICEFORGE_HOST": "192.168.1.20"})
    assert "192.168.1.20" in settings.allowed_hosts


def test_settings_wildcard_bind_keeps_loopback_only():
    settings = Settings.from_env({"VOICEFORGE_HOST": "0.0.0.0"})
    assert settings.allowed_hosts == frozenset({"localhost", "127.0.0.1", "::1"})


def test_settings_explicit_lists():
    settings = Settings.from_env(
        {
            "VOICEFORGE_ALLOWED_HOSTS": "My-PC.lan, 10.0.0.5",
            "VOICEFORGE_ALLOWED_ORIGINS": "http://localhost:3000/, https://app.example",
            "VOICEFORGE_MAX_QUEUE": "10",
        }
    )
    assert settings.allowed_hosts == frozenset({"my-pc.lan", "10.0.0.5"})
    assert settings.allowed_origins == ("http://localhost:3000", "https://app.example")
    assert settings.max_queue == 10


@pytest.mark.parametrize(
    "env",
    [
        {"VOICEFORGE_PORT": "eighty"},
        {"VOICEFORGE_PORT": "70000"},
        {"VOICEFORGE_MAX_QUEUE": "0"},
        {"VOICEFORGE_ALLOWED_ORIGINS": "*"},
    ],
)
def test_settings_reject_invalid_values(env):
    with pytest.raises(SettingsError):
        Settings.from_env(env)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("localhost:8000", "localhost"),
        ("LocalHost", "localhost"),
        ("127.0.0.1:8000", "127.0.0.1"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
        ("", ""),
    ],
)
def test_hostname_parsing(header, expected):
    assert _hostname(header) == expected
