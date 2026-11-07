"""Kokoro-ONNX text-to-speech engine wrapper.

The engine never raises at import or load time because model files are
missing. Instead it records why it is not ready, so the server can start,
report the problem through /health, and tell the user how to fix it.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger("voiceforge.engine")

MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"
DEFAULT_VOICE = "af_bella"
DEFAULT_SAMPLE_RATE = 24000

# Kokoro voice names start with a language code followed by a gender code,
# e.g. "af_bella" = American English, female. Only English voices are exposed
# because the phonemizer language has to match the voice.
VOICE_LANGUAGES = {"a": "en-us", "b": "en-gb"}

MODEL_HELP = (
    "Kokoro model files are missing. Run `python download_models.py` from the "
    "project folder, or place these files in the models/ folder manually:\n"
    f"  - {MODEL_FILE}\n"
    f"  - {VOICES_FILE}\n"
    "Both are published at "
    "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0"
)


class EngineError(Exception):
    """Base class for errors the server can report to a client."""


class EngineNotReadyError(EngineError):
    """The model is not loaded (missing files or a failed load)."""


class UnknownVoiceError(EngineError):
    """The requested voice does not exist."""


class SynthesisError(EngineError):
    """The model ran but produced no usable audio."""


def is_english_voice(name: str) -> bool:
    return len(name) > 1 and name[0] in VOICE_LANGUAGES and name[1] in "fm"


class TTSEngine:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / MODEL_FILE
        self.voices_path = self.model_dir / VOICES_FILE
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.default_voice = DEFAULT_VOICE
        self.error: str | None = None
        self._kokoro = None
        self._voices: list[str] = []
        # ONNX sessions are not safe to call concurrently from several threads.
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._kokoro is not None

    def missing_files(self) -> list[str]:
        missing = []
        if not self.model_path.is_file():
            missing.append(MODEL_FILE)
        if not self.voices_path.is_file():
            missing.append(VOICES_FILE)
        return missing

    def load(self) -> bool:
        """Load the model. Returns True on success; never raises."""
        missing = self.missing_files()
        if missing:
            self.error = f"Missing model file(s) in {self.model_dir}: {', '.join(missing)}"
            log.warning("%s. %s", self.error, MODEL_HELP)
            return False

        try:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
            self._voices = sorted(v for v in self._kokoro.get_voices() if is_english_voice(v))
            if self.default_voice not in self._voices and self._voices:
                self.default_voice = self._voices[0]
            self.error = None
            log.info("Model loaded from %s (%d English voices)", self.model_dir, len(self._voices))
            return True
        except Exception as exc:  # noqa: BLE001 - report any load failure, do not crash
            self._kokoro = None
            self.error = f"Failed to load the TTS model: {exc}"
            log.exception("Failed to load the TTS model")
            return False

    def voices(self) -> list[str]:
        return list(self._voices)

    def synthesize(self, text: str, voice: str | None = None, speed: float = 1.0) -> np.ndarray:
        """Return mono float32 audio at ``self.sample_rate``."""
        if not self.ready:
            raise EngineNotReadyError(self.error or MODEL_HELP)

        voice = voice or self.default_voice
        if voice not in self._voices:
            raise UnknownVoiceError(f"Unknown voice '{voice}'.")

        lang = VOICE_LANGUAGES[voice[0]]
        with self._lock:
            audio, sample_rate = self._kokoro.create(text, voice=voice, speed=speed, lang=lang)

        self.sample_rate = int(sample_rate)
        if audio is None or audio.size == 0:
            raise SynthesisError("The text produced no audio.")
        return audio
