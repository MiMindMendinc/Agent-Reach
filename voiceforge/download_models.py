"""Download and verify the Kokoro model files that VoiceForge needs.

Usage:
    python download_models.py            # download into ./models, verify checksums
    python download_models.py --check    # only verify files that are already there
    python download_models.py --force    # download again even if files verify
    python download_models.py --dir PATH # use a different folder

Every file is checked against a pinned SHA-256 digest, both after a download
and when it already exists. A file that does not match is never accepted.

Uses only the Python standard library. Downloads go to a temporary name and
are renamed only after they verify, so an interrupted or corrupted download
never replaces a good model.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
BASE_DIR = Path(__file__).resolve().parent
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    sha256: str


# The upstream project does not publish checksums. These digests were computed
# from the official model-files-v1.0 release assets (two independent downloads
# matched) and pin exactly those files.
FILES = (
    ModelFile(
        name="kokoro-v1.0.onnx",
        size=325_532_387,
        sha256="7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    ),
    ModelFile(
        name="voices-v1.0.bin",
        size=28_214_398,
        sha256="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    ),
)


class DownloadError(Exception):
    pass


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, spec: ModelFile) -> str | None:
    """Return None if ``path`` matches ``spec``, otherwise the reason it does not."""
    if not path.is_file():
        return "file is missing"
    size = path.stat().st_size
    if size != spec.size:
        return f"size is {size} bytes, expected {spec.size}"
    actual = sha256_of(path)
    if actual != spec.sha256:
        return f"SHA-256 is {actual}, expected {spec.sha256}"
    return None


def download(spec: ModelFile, dest: Path, base_url: str = RELEASE_URL) -> None:
    url = f"{base_url}/{spec.name}"
    temp = dest.with_name(dest.name + ".part")
    print(f"Downloading {spec.name} ({human_size(spec.size)}) ...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(temp, "wb") as out:
            total = int(response.headers.get("Content-Length") or spec.size)
            done = 0
            last_percent = -1
            while chunk := response.read(256 * 1024):
                out.write(chunk)
                done += len(chunk)
                percent = done * 100 // total if total else 0
                if percent != last_percent and percent % 10 == 0:
                    print(f"  {percent:3d}%  {human_size(done)} / {human_size(total)}")
                    last_percent = percent
    except (urllib.error.URLError, OSError) as exc:
        temp.unlink(missing_ok=True)
        raise DownloadError(f"could not download {spec.name}: {exc}") from exc

    problem = verify(temp, spec)
    if problem:
        temp.unlink(missing_ok=True)
        raise DownloadError(f"downloaded {spec.name} failed verification: {problem}")

    os.replace(temp, dest)
    print(f"  verified and saved {dest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and verify Kokoro model files for VoiceForge.")
    parser.add_argument("--dir", type=Path, default=BASE_DIR / "models", help="folder for the model files")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--force", action="store_true", help="download again even if files verify")
    mode.add_argument("--check", action="store_true", help="only verify existing files; download nothing")
    args = parser.parse_args(argv)

    target = args.dir.resolve()
    if not args.check:
        target.mkdir(parents=True, exist_ok=True)

    failures = 0
    for spec in FILES:
        dest = target / spec.name
        if not args.force:
            problem = verify(dest, spec)
            if problem is None:
                print(f"OK       {dest}")
                continue
            if args.check:
                print(f"FAILED   {dest}: {problem}", file=sys.stderr)
                failures += 1
                continue
            if dest.exists():
                print(f"Replacing {dest}: {problem}")
        try:
            download(spec, dest)
        except DownloadError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print(f"You can download it manually from {RELEASE_URL}/{spec.name}", file=sys.stderr)
            return 1

    if failures:
        print("\nRun `python download_models.py` to download verified copies.", file=sys.stderr)
        return 1

    if args.check:
        print("\nAll model files verified.")
    else:
        print(f"\nModel files are verified and ready in {target}")
        print("Start the server with: python server.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
