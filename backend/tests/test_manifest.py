"""Unit tests for Dataset Manifest integrity and provenance."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "manifests" / "dataset_manifest.json"


def test_manifest_file_exists_and_is_valid_json():
    assert MANIFEST_PATH.exists(), f"Manifest not found at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "sources" in data
    assert "manifest_version" in data


def test_manifest_contains_all_four_core_data_sources():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_names = {s.get("name", "") for s in data["sources"]}

    expected = {
        "Open-Meteo Historical Weather API",
        "Flood incident reports (manual)",
        "SRTM elevation data",
        "OpenStreetMap",
    }
    assert expected <= source_names


def test_manifest_sources_have_provenance_and_limitations():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for src in data["sources"]:
        assert "name" in src
        assert "type" in src
        assert "licence_or_attribution" in src and src["licence_or_attribution"]
        assert "local_path" in src
        assert "status" in src
        assert "data_limitations" in src and len(src["data_limitations"]) > 10


def test_manifest_files_have_accurate_sha256_checksums():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for src in data["sources"]:
        for f in src.get("files", []):
            rel_path = f["path"]
            file_path = ROOT / rel_path
            if file_path.exists():
                computed_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                assert f["sha256"] == computed_hash, f"SHA-256 mismatch for {rel_path}"

