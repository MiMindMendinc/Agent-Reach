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

The script skips files that already exist. Use `python download_models.py --force`
to download them again.

To download manually, get both files from the
[model-files-v1.0 release](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)
and place them in `models/`.

The server starts even if the files are missing. In that case the demo page
shows instructions, `/speak` returns HTTP 503 with the same instructions, and
`/health` reports what is missing.

## Configuration

Set these environment variables before starting the server, all optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `VOICEFORGE_HOST` | `127.0.0.1` | Address to listen on. Use `0.0.0.0` to let other devices on your network connect. |
| `VOICEFORGE_PORT` | `8000` | Port to listen on. |
| `VOICEFORGE_MODEL_DIR` | `./models` | Folder that contains the model files. |

Example, on macOS or Linux:

```bash
VOICEFORGE_PORT=8001 python server.py
```

VoiceForge has no authentication. Only bind to `0.0.0.0` on a network you trust.

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
| `400` | Text is empty or longer than 5,000 characters, has no letters or numbers, or the voice is unknown. |
| `422` | The text produced no audio, or a field is out of range, such as a speed of 3. |
| `503` | The model is not installed or failed to load. See `/health`. |
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
  "version": "1.0.0"
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

## Limits and behavior

- Text is limited to 5,000 characters per request. Longer text should be split by the caller.
- Speed depends on your CPU. In testing on a cloud CPU, about 4,000 characters (roughly 4 minutes of audio) took about 50 seconds to generate. Short sentences return in about a second.
- Requests are processed one at a time. Extra requests wait their turn.
- Audio is generated fresh for every request. Nothing is cached or stored.

## Troubleshooting

- **The page says the model is not installed.** Run `python download_models.py`, then restart `python server.py`.
- **`Address already in use`.** Another program is using port 8000. Start VoiceForge on a different port with `VOICEFORGE_PORT=8001`.
- **The model fails to load.** Check `/health` for the error. If a download was interrupted, run `python download_models.py --force`.
- **`pip install` fails on `numpy`, `onnxruntime`, or `soundfile`.** Upgrade pip with `python -m pip install --upgrade pip`, then try again. Make sure you are using Python 3.10 or newer.

## Project layout

```
voiceforge/
├── server.py              HTTP server and API
├── download_models.py     downloads the model files
├── tts/
│   └── engine.py          Kokoro engine wrapper
├── static/
│   └── index.html         demo page served at /
├── clients/
│   ├── python/voiceforge.py
│   └── js/voiceforge.js
├── models/                model files go here (created by download_models.py)
├── requirements.txt
└── README.md
```

## License

Released under the MIT License (see `LICENSE`). The Kokoro model and the `kokoro-onnx` library
are separate projects with their own licenses. Check their repositories before
you ship a product that uses them.
