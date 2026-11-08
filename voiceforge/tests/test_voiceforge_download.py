"""Model download and verification tests. Uses small local files, no network."""

from __future__ import annotations

import hashlib
import re

import download_models as dm
import pytest


def make_spec(content: bytes, name: str = "model.bin") -> dm.ModelFile:
    return dm.ModelFile(name=name, size=len(content), sha256=hashlib.sha256(content).hexdigest())


def test_pinned_digests_are_well_formed():
    names = {spec.name for spec in dm.FILES}
    assert names == {"kokoro-v1.0.onnx", "voices-v1.0.bin"}
    for spec in dm.FILES:
        assert re.fullmatch(r"[0-9a-f]{64}", spec.sha256)
        assert spec.size > 1_000_000


def test_verify_accepts_matching_file(tmp_path):
    content = b"model bytes"
    path = tmp_path / "model.bin"
    path.write_bytes(content)
    assert dm.verify(path, make_spec(content)) is None


def test_verify_reports_missing_wrong_size_and_wrong_hash(tmp_path):
    spec = make_spec(b"expected")
    path = tmp_path / "model.bin"
    assert dm.verify(path, spec) == "file is missing"

    path.write_bytes(b"short")
    assert "size is 5 bytes" in dm.verify(path, spec)

    path.write_bytes(b"EXPECTED")  # same size, different content
    assert "SHA-256" in dm.verify(path, spec)


def test_download_verifies_and_saves(tmp_path):
    content = b"fresh model"
    source = tmp_path / "release"
    source.mkdir()
    (source / "model.bin").write_bytes(content)
    dest = tmp_path / "models" / "model.bin"
    dest.parent.mkdir()

    dm.download(make_spec(content), dest, base_url=source.as_uri())
    assert dest.read_bytes() == content
    assert not (dest.parent / "model.bin.part").exists()


def test_corrupted_download_is_rejected_and_keeps_existing_file(tmp_path):
    source = tmp_path / "release"
    source.mkdir()
    (source / "model.bin").write_bytes(b"tampered!!!")  # same length as the expected content
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"old content")

    with pytest.raises(dm.DownloadError, match="failed verification"):
        dm.download(make_spec(b"good model!"), dest, base_url=source.as_uri())
    assert dest.read_bytes() == b"old content"
    assert not (tmp_path / "model.bin.part").exists()


def test_main_check_mode(tmp_path, monkeypatch, capsys):
    good, bad = b"good file", b"bad file"
    monkeypatch.setattr(dm, "FILES", (make_spec(good, "a.bin"), make_spec(good, "b.bin")))
    (tmp_path / "a.bin").write_bytes(good)
    (tmp_path / "b.bin").write_bytes(good)
    assert dm.main(["--check", "--dir", str(tmp_path)]) == 0

    (tmp_path / "b.bin").write_bytes(bad)
    assert dm.main(["--check", "--dir", str(tmp_path)]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_replaces_unverified_existing_file_and_keeps_good_one(tmp_path, monkeypatch):
    good = b"verified content"
    monkeypatch.setattr(dm, "FILES", (make_spec(good, "a.bin"), make_spec(good, "b.bin")))
    (tmp_path / "a.bin").write_bytes(good)
    (tmp_path / "b.bin").write_bytes(b"corrupted bytes!")

    downloaded = []

    def fake_download(spec, dest, base_url=dm.RELEASE_URL):
        downloaded.append(spec.name)
        dest.write_bytes(good)

    monkeypatch.setattr(dm, "download", fake_download)
    assert dm.main(["--dir", str(tmp_path)]) == 0
    assert downloaded == ["b.bin"]
    assert dm.verify(tmp_path / "b.bin", make_spec(good, "b.bin")) is None
