"""Test doubles for VoiceForge tests."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
from tts.engine import UnknownVoiceError


class FakeEngine:
    """Stands in for TTSEngine. Returns a short sine tone instead of speech."""

    sample_rate = 24000
    default_voice = "af_bella"
    model_dir = Path("/nonexistent")

    def __init__(
        self,
        voices: tuple[str, ...] = ("af_bella", "af_heart", "bf_emma", "bm_george"),
        fail_with: Exception | None = None,
        gate: threading.Event | None = None,
    ) -> None:
        self._voices = list(voices)
        self.fail_with = fail_with
        self.gate = gate
        self.error: str | None = None
        self.calls: list[tuple[str, str, float]] = []

    @property
    def ready(self) -> bool:
        return True

    def load(self) -> bool:
        return True

    def voices(self) -> list[str]:
        return list(self._voices)

    def missing_files(self) -> list[str]:
        return []

    def synthesize(self, text: str, voice: str | None = None, speed: float = 1.0) -> np.ndarray:
        voice = voice or self.default_voice
        if voice not in self._voices:
            raise UnknownVoiceError(f"Unknown voice '{voice}'.")
        self.calls.append((text, voice, speed))
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.fail_with is not None:
            raise self.fail_with
        t = np.arange(int(self.sample_rate * 0.25)) / self.sample_rate
        return (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
