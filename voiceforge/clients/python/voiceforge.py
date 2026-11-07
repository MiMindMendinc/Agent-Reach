"""Small Python client for a running VoiceForge server.

Uses only the standard library, so it works in any Python 3.10+ project.

    from voiceforge import VoiceForge

    vf = VoiceForge()                      # http://localhost:8000
    vf.save("Hello from my own code.", "hello.wav")
    audio = vf.speak("Bytes of a WAV file", voice="bf_emma", speed=0.9)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8000"


class VoiceForgeError(Exception):
    """Raised when the server is unreachable or returns an error."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class VoiceForge:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> bytes:
        data = None
        headers = {"Accept": "*/*"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            message = f"HTTP {exc.code}"
            try:
                body = json.loads(exc.read().decode("utf-8"))
                message = body.get("error", message)
            except (ValueError, UnicodeDecodeError):
                pass
            raise VoiceForgeError(message, status=exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise VoiceForgeError(f"Could not reach VoiceForge at {self.base_url}: {exc}") from None

    def health(self) -> dict:
        """Return the server status, including whether the model is loaded."""
        return json.loads(self._request("GET", "/health"))

    def voices(self) -> list[str]:
        """Return the available voice ids, such as ``af_bella``."""
        data = json.loads(self._request("GET", "/voices"))
        return [voice["id"] for voice in data["voices"]]

    def speak(self, text: str, voice: str | None = None, speed: float = 1.0) -> bytes:
        """Synthesize ``text`` and return WAV audio as bytes."""
        payload: dict = {"text": text, "speed": speed}
        if voice is not None:
            payload["voice"] = voice
        return self._request("POST", "/speak", payload)

    def save(self, text: str, path: str | Path, voice: str | None = None, speed: float = 1.0) -> Path:
        """Synthesize ``text`` and write the WAV file to ``path``."""
        destination = Path(path)
        destination.write_bytes(self.speak(text, voice=voice, speed=speed))
        return destination


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        sys.exit('usage: python voiceforge.py "text to speak" out.wav [voice] [speed]')
    client = VoiceForge()
    voice_arg = sys.argv[3] if len(sys.argv) > 3 else None
    speed_arg = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    try:
        saved = client.save(sys.argv[1], sys.argv[2], voice=voice_arg, speed=speed_arg)
    except VoiceForgeError as exc:
        sys.exit(f"Error: {exc}")
    print(f"Saved {saved}")
