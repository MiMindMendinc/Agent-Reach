"""Python client tests against a real HTTP server running the fake engine."""

from __future__ import annotations

import io
import sys
import threading
import time
from pathlib import Path

import pytest
import soundfile as sf
import uvicorn
from server import Settings, create_app
from voiceforge_fakes import FakeEngine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "clients" / "python"))
from voiceforge import VoiceForge, VoiceForgeError  # noqa: E402


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    app = create_app(Settings(model_dir=tmp_path_factory.mktemp("models")), FakeEngine())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_speak_returns_wav_bytes(base_url):
    audio = VoiceForge(base_url + "/").speak("Hello", voice="bm_george", speed=0.9)
    samples, sample_rate = sf.read(io.BytesIO(audio))
    assert audio[:4] == b"RIFF"
    assert sample_rate == 24000 and len(samples) > 0


def test_save_writes_file(base_url, tmp_path):
    path = VoiceForge(base_url).save("Hello", tmp_path / "out.wav")
    assert path.read_bytes()[:4] == b"RIFF"


def test_voices_and_health(base_url):
    client = VoiceForge(base_url)
    assert "af_bella" in client.voices()
    assert client.health()["model_loaded"] is True


def test_server_error_raises_with_message_and_status(base_url):
    with pytest.raises(VoiceForgeError) as info:
        VoiceForge(base_url).speak("hi", voice="nobody")
    assert info.value.status == 400
    assert "Unknown voice 'nobody'" in str(info.value)


def test_unreachable_server_raises(tmp_path):
    with pytest.raises(VoiceForgeError) as info:
        VoiceForge("http://127.0.0.1:9", timeout=2).health()
    assert info.value.status is None
    assert "Could not reach VoiceForge" in str(info.value)
