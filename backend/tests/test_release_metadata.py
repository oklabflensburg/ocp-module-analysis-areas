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
    metadata = load_release_metadata(ROOT)
    tagged = load_release_metadata(ROOT, tag=f"v{metadata.version}")
    wheel_distribution = metadata.backend_package.replace("-", "_")
    assert tagged == metadata
    assert metadata.backend_artifact.endswith(
        f"/{wheel_distribution}-{metadata.version}-py3-none-any.whl"
    )
    assert metadata.frontend_artifact.endswith(
        f"/{metadata.module_id}-{metadata.version}.tgz"
    )
    assert metadata.bundle_artifact == (
        f"dist/{metadata.module_id}-{metadata.version}.ocp"
    )


def test_release_metadata_reports_a_version_mismatch(tmp_path: Path) -> None:
    root = _release_fixture(tmp_path)
    package_path = root / "frontend/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = "99.99.99"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(ReleaseMetadataError, match="frontend package version"):
        load_release_metadata(root)


def test_release_metadata_reports_a_tag_mismatch() -> None:
    metadata = load_release_metadata(ROOT)
    with pytest.raises(ReleaseMetadataError, match="release tag"):
        load_release_metadata(ROOT, tag=f"v{metadata.version}-mismatch")
