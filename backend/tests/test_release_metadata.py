from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from scripts.release_metadata import (
    BUNDLE_FORMAT_VERSION,
    ReleaseMetadataError,
    load_release_metadata,
    verify_bundle,
)

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


def test_release_metadata_validates_embedded_bundle_metadata(tmp_path: Path) -> None:
    metadata = load_release_metadata(ROOT)
    source_commit = "a" * 40
    bundle = tmp_path / Path(metadata.bundle_artifact).name
    backend = metadata.backend_artifact.replace("backend/dist/", "backend/")
    frontend = metadata.frontend_artifact.replace("frontend/dist/", "frontend/")
    descriptor = {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "module_id": metadata.module_id,
        "version": metadata.version,
        "publisher": "oklabflensburg",
        "source": {
            "type": "local",
            "reference": f"releases/{metadata.module_id}/{metadata.version}",
        },
        "provenance": {
            "source_commit": source_commit,
            "source_tag": f"v{metadata.version}",
        },
        "manifest": {"version": metadata.version},
        "backend": {"artifact": backend},
        "frontend": {"artifact": frontend},
    }
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("module.yaml", yaml.safe_dump(descriptor))
        archive.writestr("checksums.json", "{}")
        archive.writestr(backend, b"wheel")
        archive.writestr(frontend, b"frontend")

    verify_bundle(bundle, metadata, source_commit)

    wrong_name = bundle.with_name("wrong.ocp")
    shutil.copy2(bundle, wrong_name)
    with pytest.raises(ReleaseMetadataError, match="bundle artifact name"):
        verify_bundle(wrong_name, metadata, source_commit)

    invalid_format = tmp_path / "invalid-format" / bundle.name
    invalid_format.parent.mkdir()
    descriptor["bundle_format_version"] = BUNDLE_FORMAT_VERSION + 1
    with zipfile.ZipFile(invalid_format, "w") as archive:
        archive.writestr("module.yaml", yaml.safe_dump(descriptor))
        archive.writestr("checksums.json", "{}")
        archive.writestr(backend, b"wheel")
        archive.writestr(frontend, b"frontend")
    with pytest.raises(ReleaseMetadataError, match="bundle format version"):
        verify_bundle(invalid_format, metadata, source_commit)
