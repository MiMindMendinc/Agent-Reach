"""Pytest setup for VoiceForge.

Makes `server`, `tts` and `download_models` importable from the tests.

The repository's root test run (`pytest -q` at the repository root) also
discovers this folder, but it installs a different project and not
VoiceForge's dependencies. In that environment the VoiceForge tests are not
collected. They run in the dedicated VoiceForge workflow, which installs
`requirements-dev.txt`.
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQUIRED_MODULES = ("fastapi", "httpx", "numpy", "soundfile", "uvicorn")

collect_ignore = []
if any(importlib.util.find_spec(name) is None for name in REQUIRED_MODULES):
    collect_ignore.append("tests")

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
