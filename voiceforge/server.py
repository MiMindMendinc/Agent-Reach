"""VoiceForge: a local, free text-to-speech HTTP server.

Run with:  python server.py
Then open: http://localhost:8000

Configuration is read from environment variables; see README.md for the full
list. The defaults only accept connections from this computer.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from tts.engine import (
    EngineNotReadyError,
    SynthesisError,
    TTSEngine,
    UnknownVoiceError,
    is_english_voice,
)

__version__ = "1.1.0"

BASE_DIR = Path(__file__).resolve().parent
MAX_TEXT_CHARS = 5000
# 5,000 characters of JSON-escaped UTF-8 text fits comfortably in 64 KiB.
MAX_BODY_BYTES = 64 * 1024
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
WILDCARD_BIND_ADDRESSES = frozenset({"0.0.0.0", "::", ""})
ACCENTS = {"a": "US", "b": "UK"}
GENDERS = {"f": "female", "m": "male"}

log = logging.getLogger("voiceforge")


# --- Settings ---------------------------------------------------------------

class SettingsError(ValueError):
    """An environment variable has an invalid value."""


def _int_env(environ: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a whole number, got {raw!r}.") from None
    if not low <= value <= high:
        raise SettingsError(f"{name} must be between {low} and {high}, got {value}.")
    return value


def _csv_env(environ: Mapping[str, str], name: str) -> list[str]:
    return [item.strip() for item in environ.get(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    model_dir: Path = BASE_DIR / "models"
    # Hostnames accepted in the Host header ("*" accepts any). Rejecting
    # unknown names protects the local server from DNS-rebinding pages.
    allowed_hosts: frozenset[str] = LOOPBACK_HOSTS
    # Extra browser origins allowed to call the API cross-origin.
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    # Synthesis runs one request at a time; this caps how many may wait.
    max_queue: int = 4
    max_body_bytes: int = MAX_BODY_BYTES

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        host = env.get("VOICEFORGE_HOST", "127.0.0.1").strip()

        allowed_hosts = {h.lower().strip("[]") for h in _csv_env(env, "VOICEFORGE_ALLOWED_HOSTS")}
        if not allowed_hosts:
            allowed_hosts = set(LOOPBACK_HOSTS)
            if host not in WILDCARD_BIND_ADDRESSES:
                allowed_hosts.add(host.lower().strip("[]"))

        origins = tuple(o.rstrip("/").lower() for o in _csv_env(env, "VOICEFORGE_ALLOWED_ORIGINS"))
        if "*" in origins:
            raise SettingsError(
                "VOICEFORGE_ALLOWED_ORIGINS does not accept '*'. List each origin, "
                "for example http://localhost:3000."
            )

        return cls(
            host=host,
            port=_int_env(env, "VOICEFORGE_PORT", 8000, 1, 65535),
            model_dir=Path(env.get("VOICEFORGE_MODEL_DIR") or BASE_DIR / "models"),
            allowed_hosts=frozenset(allowed_hosts),
            allowed_origins=origins,
            max_queue=_int_env(env, "VOICEFORGE_MAX_QUEUE", 4, 1, 1000),
        )


# --- Request guard ----------------------------------------------------------

def _hostname(host_header: str) -> str:
    """Return the host part of a Host header, without port or IPv6 brackets."""
    value = host_header.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


async def _reject(scope: Scope, receive: Receive, send: Send, status: int, message: str) -> None:
    await JSONResponse({"error": message}, status_code=status)(scope, receive, send)


class RequestGuard:
    """Checks the Host header, the Origin header and the body size.

    Runs before any route so that oversized or cross-site requests are
    rejected before their body is parsed.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    def _host_allowed(self, host: str) -> bool:
        return "*" in self.settings.allowed_hosts or host in self.settings.allowed_hosts

    def _origin_allowed(self, origin: str, scope: Scope, host_header: str) -> bool:
        origin = origin.rstrip("/").lower()
        same_origin = f"{scope.get('scheme', 'http')}://{host_header.lower()}"
        return origin == same_origin or origin in self.settings.allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        host_header = headers.get("host", "")
        if not self._host_allowed(_hostname(host_header)):
            await _reject(
                scope, receive, send, 400,
                "Host not allowed. Add it to VOICEFORGE_ALLOWED_HOSTS to accept it.",
            )
            return

        origin = headers.get("origin")
        if origin is not None and not self._origin_allowed(origin, scope, host_header):
            await _reject(
                scope, receive, send, 403,
                "Cross-origin requests are not allowed. Add the origin to "
                "VOICEFORGE_ALLOWED_ORIGINS to accept it.",
            )
            return

        limit = self.settings.max_body_bytes
        too_large = f"Request body is too large (maximum {limit} bytes)."
        content_length = headers.get("content-length")
        if content_length is not None:
            if not content_length.isdigit():
                await _reject(scope, receive, send, 400, "Invalid Content-Length header.")
                return
            if int(content_length) > limit:
                await _reject(scope, receive, send, 413, too_large)
                return

        # Also enforce the limit while streaming, for requests sent without a
        # Content-Length header (chunked transfer encoding). FastAPI turns an
        # HTTPException raised while reading the body into the error response.
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, too_large)
            return message

        await self.app(scope, limited_receive, send)


# --- Application ------------------------------------------------------------

class SpeakRequest(BaseModel):
    text: str = Field(default="", description=f"Text to speak (max {MAX_TEXT_CHARS} characters).")
    voice: str | None = Field(default=None, description="Voice id, e.g. af_bella. See GET /voices.")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking rate, 0.5 to 2.0.")


def voice_details(voice_id: str) -> dict[str, str]:
    name = voice_id[3:].replace("_", " ").title()
    accent = ACCENTS.get(voice_id[0], "")
    gender = GENDERS.get(voice_id[1], "")
    return {
        "id": voice_id,
        "label": f"{name} ({accent}, {gender})",
        "accent": accent,
        "gender": gender,
    }


def create_app(settings: Settings | None = None, engine: Any = None) -> FastAPI:
    """Build the VoiceForge app. Tests pass their own settings and engine."""
    settings = settings or Settings.from_env()
    engine = engine if engine is not None else TTSEngine(settings.model_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Loading takes about a second. A missing model is not fatal: the
        # server still starts and /health explains what to fix.
        if not engine.ready:
            await run_in_threadpool(engine.load)
        if not engine.ready:
            log.warning("Server is running, but speech is unavailable until the model is installed.")
        yield

    app = FastAPI(title="VoiceForge", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.pending = 0

    # Every error response has the shape {"error": "<message>"}, and no stack
    # traces are sent to callers.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            {"error": str(exc.detail)},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(err.get("type") == "json_invalid" for err in errors):
            return JSONResponse({"error": "Request body must be valid JSON."}, status_code=422)
        problems = []
        for err in errors:
            loc = [str(part) for part in err.get("loc", ()) if part != "body"]
            msg = err.get("msg", "invalid value")
            problems.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
        return JSONResponse({"error": "Invalid request. " + "; ".join(problems)}, status_code=422)

    @app.post("/speak", response_class=Response)
    async def speak(req: SpeakRequest):
        text = req.text.strip()
        if not text:
            raise HTTPException(400, "Text is required.")
        if len(text) > MAX_TEXT_CHARS:
            raise HTTPException(
                400, f"Text is too long ({len(text)} characters; the maximum is {MAX_TEXT_CHARS})."
            )
        if not any(ch.isalnum() for ch in text):
            raise HTTPException(400, "Nothing to speak: the text must contain letters or numbers.")

        if app.state.pending >= settings.max_queue:
            raise HTTPException(
                503, "VoiceForge is busy. Try again in a moment.", headers={"Retry-After": "2"}
            )

        log.info(
            "Speak request: %d characters (voice=%s, speed=%.2f)",
            len(text), req.voice or engine.default_voice, req.speed,
        )
        app.state.pending += 1
        try:
            audio = await run_in_threadpool(engine.synthesize, text, req.voice, req.speed)
        except EngineNotReadyError as exc:
            raise HTTPException(503, str(exc)) from None
        except UnknownVoiceError as exc:
            raise HTTPException(400, f"{exc} See GET /voices for the list of voices.") from None
        except SynthesisError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            log.exception("Synthesis failed")
            raise HTTPException(
                500, "Speech synthesis failed. Check the server log for details."
            ) from None
        finally:
            app.state.pending -= 1

        buffer = io.BytesIO()
        sf.write(buffer, audio, engine.sample_rate, format="WAV", subtype="PCM_16")
        return Response(
            content=buffer.getvalue(),
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/voices")
    async def voices():
        if not engine.ready:
            raise HTTPException(503, engine.error or "Model not loaded. See GET /health.")
        return {
            "default": engine.default_voice,
            "voices": [voice_details(v) for v in engine.voices() if is_english_voice(v)],
        }

    @app.get("/health")
    async def health():
        ready = engine.ready
        return {
            "status": "ok" if ready else "degraded",
            "model_loaded": ready,
            "voices": len(engine.voices()),
            "missing_files": engine.missing_files(),
            "error": engine.error,
            "version": __version__,
        }

    # Demo page, mounted last so the API routes above take precedence.
    static_dir = BASE_DIR / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # Middleware: the last one added runs first.
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )
    app.add_middleware(RequestGuard, settings=settings)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "%s %s -> %d (%.0f ms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        sys.exit(f"Configuration error: {exc}")

    engine = TTSEngine(settings.model_dir)
    application = create_app(settings, engine)

    display_host = "localhost" if settings.host in WILDCARD_BIND_ADDRESSES | {"127.0.0.1"} else settings.host
    print(f"\nVoiceForge {__version__} starting on http://{display_host}:{settings.port}")
    if settings.host in WILDCARD_BIND_ADDRESSES and settings.allowed_hosts == LOOPBACK_HOSTS:
        print(
            "Listening on all network interfaces, but only localhost names are accepted.\n"
            "Set VOICEFORGE_ALLOWED_HOSTS to this machine's name or IP address to allow "
            "other devices."
        )
    if engine.missing_files():
        print("Speech is unavailable until the model is installed. Run: python download_models.py\n")

    uvicorn.run(application, host=settings.host, port=settings.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
else:
    # For `uvicorn server:app`. When run as a script, main() builds the app so
    # that configuration errors are reported cleanly instead of as a traceback.
    app = create_app()
