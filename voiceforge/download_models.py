"""Download the Kokoro model files that VoiceForge needs.

Usage:
    python download_models.py            # download into ./models
    python download_models.py --force    # re-download even if files exist
    python download_models.py --dir PATH # download somewhere else

Uses only the Python standard library. Files are downloaded to a temporary
name and renamed only when complete, so an interrupted download never leaves
a broken model behind.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {
    "kokoro-v1.0.onnx": 300_000_000,  # rough minimum size, used to catch truncated downloads
    "voices-v1.0.bin": 20_000_000,
}
BASE_DIR = Path(__file__).resolve().parent


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def download(name: str, dest: Path) -> None:
    url = f"{RELEASE_URL}/{name}"
    temp = dest.with_suffix(dest.suffix + ".part")
    print(f"Downloading {name} ...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(temp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            last_percent = -1
            while chunk := response.read(1024 * 256):
                out.write(chunk)
                done += len(chunk)
                if total:
                    percent = done * 100 // total
                    if percent != last_percent and percent % 5 == 0:
                        print(f"  {percent:3d}%  {human_size(done)} / {human_size(total)}")
                        last_percent = percent
    except (urllib.error.URLError, OSError) as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download {name}: {exc}") from exc

    size = temp.stat().st_size
    if size < FILES[name]:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"{name} looks incomplete ({human_size(size)}). Run the script again.")

    os.replace(temp, dest)
    print(f"  saved {dest} ({human_size(size)})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Kokoro model files for VoiceForge.")
    parser.add_argument("--dir", type=Path, default=BASE_DIR / "models", help="folder to store the models in")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = parser.parse_args()

    target = args.dir.resolve()
    target.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        dest = target / name
        if dest.is_file() and not args.force:
            print(f"Already present: {dest}")
            continue
        try:
            download(name, dest)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print(f"You can also download {name} manually from {RELEASE_URL}/{name}", file=sys.stderr)
            return 1

    print(f"\nModel files are ready in {target}")
    print("Start the server with: python server.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
