#!/usr/bin/env python3
"""Validate and expose the canonical release metadata."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import tomllib
import yaml

SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$")
BUNDLE_FORMAT_VERSION = 1


class ReleaseMetadataError(ValueError):
    """Raised when release metadata is inconsistent."""


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    module_id: str
    backend_package: str
    frontend_package: str
    backend_artifact: str
    frontend_artifact: str
    bundle_artifact: str


def _module_manifest(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "MANIFEST" for target in node.targets)
            and isinstance(node.value, ast.Call)
            and node.value.args
        ):
            value = ast.literal_eval(node.value.args[0])
            if isinstance(value, dict):
                return value
    raise ReleaseMetadataError(f"Could not find a literal MANIFEST definition in {path}")


def _require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ReleaseMetadataError(f"{label} must be {expected!r}, got {actual!r}")


def load_release_metadata(repo_root: Path, *, tag: str | None = None) -> ReleaseMetadata:
    root = repo_root.resolve()
    manifest = yaml.safe_load((root / "module.yaml").read_text(encoding="utf-8"))
    backend = tomllib.loads((root / "backend/pyproject.toml").read_text(encoding="utf-8"))
    backend_manifest = _module_manifest(
        root / "backend/src/ocp_module_analysis_areas/module.py"
    )
    frontend_package = json.loads(
        (root / "frontend/package.json").read_text(encoding="utf-8")
    )
    frontend_manifest = json.loads(
        (root / "frontend/module.json").read_text(encoding="utf-8")
    )

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ReleaseMetadataError(f"module.yaml version is not valid SemVer: {version!r}")
    module_id = manifest.get("id")
    if not isinstance(module_id, str) or not module_id:
        raise ReleaseMetadataError("module.yaml id must be a non-empty string")
    backend_package = manifest.get("backend", {}).get("package")
    frontend_name = manifest.get("frontend", {}).get("package")
    if not isinstance(backend_package, str) or not isinstance(frontend_name, str):
        raise ReleaseMetadataError("module.yaml must declare backend and frontend package names")

    _require_equal("backend project version", backend["project"]["version"], version)
    _require_equal("backend module manifest version", backend_manifest.get("version"), version)
    _require_equal("frontend package version", frontend_package.get("version"), version)
    _require_equal("frontend module version", frontend_manifest.get("version"), version)
    _require_equal("backend project identity", backend["project"]["name"], backend_package)
    _require_equal("backend module identity", backend_manifest.get("id"), module_id)
    _require_equal("backend module package", backend_manifest.get("backend", {}).get("package"), backend_package)
    _require_equal("frontend package identity", frontend_package.get("name"), frontend_name)
    _require_equal("frontend module identity", frontend_manifest.get("id"), module_id)
    _require_equal("frontend backend module identity", frontend_manifest.get("backendModuleId"), module_id)
    if tag is not None:
        _require_equal("release tag", tag, f"v{version}")

    wheel_distribution = backend_package.replace("-", "_")
    return ReleaseMetadata(
        version=version,
        module_id=module_id,
        backend_package=backend_package,
        frontend_package=frontend_name,
        backend_artifact=f"backend/dist/{wheel_distribution}-{version}-py3-none-any.whl",
        frontend_artifact=f"frontend/dist/{module_id}-{version}.tgz",
        bundle_artifact=f"dist/{module_id}-{version}.ocp",
    )


def verify_bundle(path: Path, metadata: ReleaseMetadata, source_commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", source_commit):
        raise ReleaseMetadataError(f"Invalid source commit: {source_commit!r}")
    expected_members = {
        "module.yaml",
        "checksums.json",
        metadata.backend_artifact.replace("backend/dist/", "backend/"),
        metadata.frontend_artifact.replace("frontend/dist/", "frontend/"),
    }
    _require_equal("bundle artifact name", path.name, Path(metadata.bundle_artifact).name)
    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())
        if members != expected_members:
            raise ReleaseMetadataError(
                f"Unexpected bundle members: expected {sorted(expected_members)!r}, got {sorted(members)!r}"
            )
        bundled = yaml.safe_load(archive.read("module.yaml"))
    expected = {
        "bundle format version": (
            bundled.get("bundle_format_version"),
            BUNDLE_FORMAT_VERSION,
        ),
        "module id": (bundled.get("module_id"), metadata.module_id),
        "bundle version": (bundled.get("version"), metadata.version),
        "manifest version": (bundled.get("manifest", {}).get("version"), metadata.version),
        "publisher": (bundled.get("publisher"), "oklabflensburg"),
        "source reference": (
            bundled.get("source", {}).get("reference"),
            f"releases/{metadata.module_id}/{metadata.version}",
        ),
        "source commit": (
            bundled.get("provenance", {}).get("source_commit"),
            source_commit,
        ),
        "source tag": (
            bundled.get("provenance", {}).get("source_tag"),
            f"v{metadata.version}",
        ),
        "backend component": (
            bundled.get("backend", {}).get("artifact"),
            metadata.backend_artifact.replace("backend/dist/", "backend/"),
        ),
        "frontend component": (
            bundled.get("frontend", {}).get("artifact"),
            metadata.frontend_artifact.replace("frontend/dist/", "frontend/"),
        ),
    }
    for label, (actual, wanted) in expected.items():
        _require_equal(label, actual, wanted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag")
    parser.add_argument("--field", choices=tuple(ReleaseMetadata.__annotations__))
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--verify-bundle", type=Path)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    try:
        metadata = load_release_metadata(args.repo_root, tag=args.tag)
        if args.verify_bundle:
            if not args.source_commit:
                parser.error("--verify-bundle requires --source-commit")
            verify_bundle(args.verify_bundle, metadata, args.source_commit)
        if args.github_env:
            with args.github_env.open("a", encoding="utf-8") as environment:
                environment.write(f"MODULE_VERSION={metadata.version}\n")
                environment.write(f"MODULE_ID={metadata.module_id}\n")
                environment.write(f"BUNDLE_ARTIFACT={metadata.bundle_artifact}\n")
                environment.write(f"BUNDLE_CHECKSUM={metadata.bundle_artifact}.sha256\n")
        if args.field:
            print(getattr(metadata, args.field))
        elif not args.github_env and not args.verify_bundle:
            print(json.dumps(asdict(metadata), sort_keys=True))
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, yaml.YAMLError) as exc:
        print(f"release metadata validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
