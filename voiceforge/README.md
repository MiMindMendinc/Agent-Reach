# VoiceForge

A local, free, high-quality text-to-speech server. Speech is generated on your
machine by the open-source [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M)
model running through ONNX. There are no API keys, no accounts, and no network
calls at runtime. Any app that can make an HTTP request can use it.

## Requirements

- Python 3.10 or newer
- About 350 MB of disk space for the model files
- Windows, macOS, or Linux. Speech runs on the CPU, so no GPU is needed.

## Quick start

Run these commands from the `voiceforge` folder:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python download_models.py          # one-time, downloads about 350 MB
python server.py
```

Then open **http://localhost:8000** in your browser, type something, and press
**Speak** (or **Ctrl/⌘ + Enter**).

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

## Model files

`download_models.py` saves two files into `models/`:

| File | Size | Purpose |
| --- | --- | --- |
| `kokoro-v1.0.onnx` | ~310 MB | the speech model |
| `voices-v1.0.bin` | ~27 MB | voice embeddings |

Both files are checked against pinned SHA-256 checksums, after every download
and when they already exist. A file that does not match is replaced, and a
download that does not match is discarded, so a corrupted or tampered file is
never used. The upstream project does not publish checksums, so the pinned
values were computed from its official `model-files-v1.0` release files.

| Command | What it does |
| --- | --- |
| `python download_models.py` | downloads missing or unverified files |
| `python download_models.py --check` | verifies the files you have, downloads nothing |
| `python download_models.py --force` | downloads both files again |

To download manually, get both files from the
[model-files-v1.0 release](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0),
place them in `models/`, and run `python download_models.py --check`.

The server starts even if the files are missing. In that case the demo page
shows instructions, `/speak` returns HTTP 503 with the same instructions, and
`/health` reports what is missing.

## Configuration

Set these environment variables before starting the server, all optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `VOICEFORGE_HOST` | `127.0.0.1` | Address to listen on. Use `0.0.0.0` to listen on every network interface. |
| `VOICEFORGE_PORT` | `8000` | Port to listen on. |
| `VOICEFORGE_MODEL_DIR` | `./models` | Folder that contains the model files. |
| `VOICEFORGE_ALLOWED_HOSTS` | `localhost,127.0.0.1,::1` | Comma-separated host names accepted in requests. `*` accepts any. |
| `VOICEFORGE_ALLOWED_ORIGINS` | none | Comma-separated web origins, such as `http://localhost:3000`, that may call the API from a browser. |
| `VOICEFORGE_MAX_QUEUE` | `4` | Most speech requests allowed to run or wait at once. Extra requests get HTTP 503. |

Example, on macOS or Linux:

```bash
VOICEFORGE_PORT=8001 python server.py
```

### Security defaults

VoiceForge is built to run on your own computer. By default:

- It listens only on `127.0.0.1`, so other devices cannot connect.
- It accepts only the host names `localhost`, `127.0.0.1` and `::1`. This stops
  a malicious web page from reaching it through DNS rebinding.
- It rejects browser requests from other websites (`Origin` checks). Only the
  built-in demo page, and any origins you list in `VOICEFORGE_ALLOWED_ORIGINS`,
  can call it from a browser. Scripts and apps that are not browsers are unaffected.
- Request bodies are limited to 64 KB, and at most `VOICEFORGE_MAX_QUEUE`
  speech requests run or wait at once.

VoiceForge has no authentication. To use it from other devices, set
`VOICEFORGE_HOST=0.0.0.0` and add this computer's name or IP address to
`VOICEFORGE_ALLOWED_HOSTS`, and only do this on a network you trust:

```bash
VOICEFORGE_HOST=0.0.0.0 VOICEFORGE_ALLOWED_HOSTS=192.168.1.20,localhost python server.py
```

## HTTP API

Errors always return JSON in the form `{"error": "message"}`.

### `POST /speak`

Request body (JSON):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `text` | string | required | 1 to 5,000 characters, must include letters or numbers |
| `voice` | string | server default | a voice id from `GET /voices` |
| `speed` | number | `1.0` | from `0.5` (slow) to `2.0` (fast) |

Response: `200 OK` with `Content-Type: audio/wav` (16-bit PCM, 24 kHz, mono).

```bash
curl -X POST http://localhost:8000/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from VoiceForge", "voice": "af_bella", "speed": 1.0}' \
  --output hello.wav
```

| Status | Meaning |
| --- | --- |
| `400` | Text is empty or longer than 5,000 characters, has no letters or numbers, or the voice is unknown. Also returned for a host name that is not allowed. |
| `403` | A browser request came from a website that is not allowed. See `VOICEFORGE_ALLOWED_ORIGINS`. |
| `413` | The request body is larger than 64 KB. |
| `422` | The body is not valid JSON, a field is out of range (such as a speed of 3), or the text produced no audio. |
| `503` | The model is not installed or failed to load (see `/health`), or the server is busy. A busy response includes a `Retry-After` header. |
| `500` | An unexpected error. Details are written to the server log, not sent to the client. |

### `GET /voices`

Returns the default voice and the English voices that are available:

```json
{
  "default": "af_bella",
  "voices": [
    {"id": "af_bella", "label": "Bella (US, female)", "accent": "US", "gender": "female"},
    {"id": "bm_george", "label": "George (UK, male)", "accent": "UK", "gender": "male"}
  ]
}
```

Voice ids starting with `a` are US English and ids starting with `b` are UK English.
The model also includes other languages, which VoiceForge does not expose yet.

### `GET /health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "voices": 28,
  "missing_files": [],
  "error": null,
  "version": "1.1.0"
}
```

`status` is `ok` when the model is loaded and `degraded` otherwise. The endpoint
returns HTTP 200 in both cases, so it works as a liveness check too.

## Using VoiceForge from your code

### Python

Copy `clients/python/voiceforge.py` into your project. It uses only the standard
library.

```python
from voiceforge import VoiceForge

vf = VoiceForge()                        # http://localhost:8000
vf.save("Your build finished.", "done.wav")

audio_bytes = vf.speak("Slower, please.", voice="bf_emma", speed=0.9)
print(vf.voices())
```

Errors raise `VoiceForgeError`, with the server's message in `str(err)`.

### JavaScript (browser or Node 18+)

Copy `clients/js/voiceforge.js` into your project.

```js
import { VoiceForge } from "./voiceforge.js";

const vf = new VoiceForge();                       // http://localhost:8000
const wav = await vf.speak("Hello there", { voice: "af_heart", speed: 1.1 });

const audio = new Audio(URL.createObjectURL(wav));
await audio.play();
```

`speak()` returns a `Blob` containing WAV audio. Errors throw `VoiceForgeError`.
The `timeoutMs` option (default 120 seconds) covers the whole request,
including downloading the audio.

A web page served from a different origin, for example a dev server on
`http://localhost:3000`, must be listed in `VOICEFORGE_ALLOWED_ORIGINS`.
Otherwise the browser request is rejected with HTTP 403.

## Limits and behavior

- Text is limited to 5,000 characters per request. Longer text should be split by the caller.
- Speed depends on your CPU. In testing on a cloud CPU, about 4,000 characters (roughly 4 minutes of audio) took about 50 seconds to generate. Short sentences return in about a second.
- Speech requests are processed one at a time. Up to `VOICEFORGE_MAX_QUEUE` requests (default 4) may run or wait. Beyond that, VoiceForge answers HTTP 503 so callers can retry, instead of queuing without limit.
- Audio is generated fresh for every request. Nothing is cached or stored.

## Troubleshooting

- **The page says the model is not installed.** Run `python download_models.py`, then restart `python server.py`.
- **`Address already in use`.** Another program is using port 8000. Start VoiceForge on a different port with `VOICEFORGE_PORT=8001`.
- **The model fails to load.** Run `python download_models.py --check`. If a file fails, run `python download_models.py` to replace it.
- **`Host not allowed`.** You reached VoiceForge by a name it does not accept, such as your computer's network name. Add that name to `VOICEFORGE_ALLOWED_HOSTS`.
- **`Cross-origin requests are not allowed`.** A web page on another origin called the API. Add that origin to `VOICEFORGE_ALLOWED_ORIGINS`.
- **`pip install` fails on `numpy`, `onnxruntime`, or `soundfile`.** Upgrade pip with `python -m pip install --upgrade pip`, then try again. Make sure you are using Python 3.10 or newer.

## Development

Tests use a fake speech engine, so they need neither the model files nor a network connection.

```bash
pip install -r requirements-dev.txt
ruff check .
pytest tests -q
node --test clients/js/voiceforge.test.mjs      # needs Node 18 or newer
```

The `voiceforge` GitHub Actions workflow runs the same checks on Python 3.10 to 3.13,
plus a `pip-audit` scan of the pinned dependencies.

## Project layout

```
voiceforge/
├── server.py              HTTP server, API and request checks
├── download_models.py     downloads and verifies the model files
├── tts/
│   └── engine.py          Kokoro engine wrapper
├── static/
│   └── index.html         demo page served at /
├── clients/
│   ├── python/voiceforge.py
│   └── js/                voiceforge.js and its tests
├── tests/                 pytest suite (no model needed)
├── models/                model files go here (created by download_models.py)
├── requirements.txt       pinned runtime dependencies
├── requirements-dev.txt   adds test and lint tools
├── LICENSE
└── README.md
```

## License

Released under the MIT License (see `LICENSE`). The Kokoro model and the `kokoro-onnx` library
are separate projects with their own licenses. Check their repositories before
you ship a product that uses them.
