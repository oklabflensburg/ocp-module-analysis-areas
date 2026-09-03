from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scripts.release_metadata import ReleaseMetadataError, load_release_metadata

ROOT = Path(__file__).resolve().parents[2]


def _release_fixture(tmp_path: Path) -> Path:
    for relative in (
        "module.yaml",
        "backend/pyproject.toml",
        "backend/src/ocp_module_analysis_areas/module.py",
        "frontend/package.json",
        "frontend/module.json",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def test_release_metadata_accepts_the_canonical_release() -> None:
    metadata = load_release_metadata(ROOT, tag="v1.5.0")
    assert metadata.backend_artifact.endswith(
        "/ocp_module_analysis_areas-1.5.0-py3-none-any.whl"
    )
    assert metadata.frontend_artifact.endswith("/analysis-areas-1.5.0.tgz")
    assert metadata.bundle_artifact == "dist/analysis-areas-1.5.0.ocp"


def test_release_metadata_reports_a_version_mismatch(tmp_path: Path) -> None:
    root = _release_fixture(tmp_path)
    package_path = root / "frontend/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = "1.5.1"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(ReleaseMetadataError, match="frontend package version"):
        load_release_metadata(root, tag="v1.5.0")


def test_release_metadata_reports_a_tag_mismatch() -> None:
    with pytest.raises(ReleaseMetadataError, match="release tag"):
        load_release_metadata(ROOT, tag="v1.5.1")
