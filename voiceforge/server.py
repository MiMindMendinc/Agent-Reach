"""VoiceForge: a local, free text-to-speech HTTP server.

Run with:  python server.py
Then open: http://localhost:8000

Environment variables (all optional):
  VOICEFORGE_HOST       address to listen on (default 127.0.0.1)
  VOICEFORGE_PORT       port to listen on (default 8000)
  VOICEFORGE_MODEL_DIR  folder containing the Kokoro model files (default ./models)
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from tts.engine import (
    EngineNotReadyError,
    SynthesisError,
    TTSEngine,
    UnknownVoiceError,
    is_english_voice,
)

__version__ = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent
MAX_TEXT_CHARS = 5000
ACCENTS = {"a": "US", "b": "UK"}
GENDERS = {"f": "female", "m": "male"}

log = logging.getLogger("voiceforge")

MODEL_DIR = Path(os.environ.get("VOICEFORGE_MODEL_DIR", BASE_DIR / "models"))
engine = TTSEngine(MODEL_DIR)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Loading takes about a second. A missing model is not fatal: the server
    # still starts and /health explains what to fix.
    await run_in_threadpool(engine.load)
    if not engine.ready:
        log.warning("Server is running, but speech is unavailable until the model is installed.")
    yield


app = FastAPI(title="VoiceForge", version=__version__, lifespan=lifespan)


class SpeakRequest(BaseModel):
    text: str = Field(default="", description=f"Text to speak (max {MAX_TEXT_CHARS} characters).")
    voice: str | None = Field(default=None, description="Voice id, e.g. af_bella. See GET /voices.")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking rate, 0.5 to 2.0.")


# --- Errors -----------------------------------------------------------------
# Every error response has the shape {"error": "<message>"}. Clients can rely
# on that, and no stack traces are sent to callers.

@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    if any(err.get("type") == "json_invalid" for err in exc.errors()):
        return JSONResponse({"error": "Request body must be valid JSON."}, status_code=422)

    problems = []
    for err in exc.errors():
        field = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
        problems.append(f"{field}: {err.get('msg', 'invalid value')}" if field else err.get("msg", "invalid request"))
    return JSONResponse({"error": "Invalid request. " + "; ".join(problems)}, status_code=422)


# --- Request logging --------------------------------------------------------

@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


# --- API --------------------------------------------------------------------

def voice_details(voice_id: str) -> dict:
    name = voice_id[3:].replace("_", " ").title()
    accent = ACCENTS.get(voice_id[0], "")
    gender = GENDERS.get(voice_id[1], "")
    return {
        "id": voice_id,
        "label": f"{name} ({accent}, {gender})",
        "accent": accent,
        "gender": gender,
    }


@app.post("/speak", response_class=Response)
async def speak(req: SpeakRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Text is required.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"Text is too long ({len(text)} characters; the maximum is {MAX_TEXT_CHARS}).")
    if not any(ch.isalnum() for ch in text):
        raise HTTPException(400, "Nothing to speak: the text must contain letters or numbers.")

    log.info("Speak request: %d characters (voice=%s, speed=%.2f)", len(text), req.voice or engine.default_voice, req.speed)
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
        raise HTTPException(500, "Speech synthesis failed. Check the server log for details.") from None

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


# --- Demo page --------------------------------------------------------------
# Mounted last so the API routes above take precedence.
static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    host = os.environ.get("VOICEFORGE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("VOICEFORGE_PORT", "8000"))
    except ValueError:
        sys.exit("VOICEFORGE_PORT must be a number.")

    display_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"\nVoiceForge {__version__} starting on http://{display_host}:{port}")
    if engine.missing_files():
        print("Speech is unavailable until the model is installed. Run: python download_models.py\n")

    uvicorn.run(app, host=host, port=port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
