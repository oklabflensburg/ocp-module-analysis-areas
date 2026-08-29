from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ADOPTED_FILES = {
    "20260814_0014": "20260814_0014_analysis_areas.py",
    "20260817_0023": "20260817_0023_area_wikidata.py",
    "20260818_0025": "20260818_0025_osm_external_links.py",
    "20260819_0032": "20260819_0032_optimize_area_poi_analytics.py",
}
EXPECTED_HEAD = "20260825_0034"


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    host = Path(sys.argv[1]).resolve()
    bundle = Path(sys.argv[2]).resolve()
    contract = json.loads(
        (repository / ".github/ocp-host-contract.json").read_text(encoding="utf-8")
    )
    expected = contract["commit"]
    actual = subprocess.run(
        ["git", "-C", str(host), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise SystemExit(f"Host contract mismatch: expected {expected}, got {actual}")

    os.chdir(host / "backend")

    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.cli import module_migrations
    from app.cli.modules import _installer
    from app.platform.modules import installer as installer_module
    from app.platform.modules.bundle import staged_ocp_bundle
    from app.platform.modules.discovery import (
        EntryPointModuleDiscovery,
        FirstPartyModuleDiscovery,
        scoped_module_python_paths,
    )
    from app.platform.modules.errors import ModulePersistenceError
    from app.platform.modules.installer import installed_backend_distribution_paths
    from app.platform.modules.migrations import MigrationCoordinator
    from app.platform.modules.persistence import (
        build_persistence_registry,
        resolve_available_persistence_definitions,
    )
    from app.platform.modules.runtime import MODULE_SDK_VERSION

    if MODULE_SDK_VERSION != contract["sdk_version"]:
        raise AssertionError(
            f"Host SDK mismatch: expected {contract['sdk_version']}, got {MODULE_SDK_VERSION}"
        )

    class CutoverDiscovery(FirstPartyModuleDiscovery):
        def __init__(self) -> None:
            super().__init__({})

    # The built-in/external ID and frontend collisions remain #188 concerns.
    # Keep that cutover simulation scoped; migration discovery itself uses the
    # normal installed-entry-point and host coordinator contracts below.
    installer_module.FirstPartyModuleDiscovery = CutoverDiscovery
    module_migrations.FirstPartyModuleDiscovery = CutoverDiscovery

    builtin_frontend = host / "frontend/frontend-modules/analysis-areas"
    parked_frontend = host / "frontend/.analysis-areas.builtin-contract-test"
    if parked_frontend.exists():
        raise SystemExit(f"Temporary cutover path already exists: {parked_frontend}")

    builtin_frontend.rename(parked_frontend)
    try:
        os.environ.update({"ENABLED_MODULES": "", "OCP_FRONTEND_MODULES": ""})
        with TemporaryDirectory(prefix="ocp-analysis-areas-contract-") as temporary:
            root = Path(temporary)
            installer = _installer(root)
            with staged_ocp_bundle(bundle) as (package_root, package):
                verified = installer.verify_installable(package_root)
                assert verified.bundle_sha256 == package.bundle_sha256
            with staged_ocp_bundle(bundle) as (package_root, _package):
                installed = installer.install(package_root)

            # Installation is passive: migration history is discoverable while
            # runtime activation and its permanent Python path remain disabled.
            assert installed.enabled is False
            assert installer.enablement_environment().runtime_backend_paths == ""
            installed_paths = installed_backend_distribution_paths(root)
            assert len(installed_paths) == 1
            history = installed_paths[0] / "ocp_module_analysis_areas/migrations/history"
            assert {path.name for path in history.glob("*.py")} == {
                "__init__.py",
                *ADOPTED_FILES.values(),
            }

            # Characterize the actual installed wheel against the pinned host.
            host_versions = host / "backend/alembic/versions"
            for filename in ADOPTED_FILES.values():
                assert (history / filename).read_bytes() == (host_versions / filename).read_bytes()

            python_path_before = sys.path.copy()
            with scoped_module_python_paths(installed_paths):
                available = resolve_available_persistence_definitions(
                    (
                        CutoverDiscovery(),
                        EntryPointModuleDiscovery(distribution_paths=installed_paths),
                    )
                )
                assert len(available) == 1
                definition, manifest = available[0]
                assert manifest.id == "analysis-areas"
                assert manifest.persistence is not None
                assert manifest.persistence.migrations is True
                assert definition.persistence is not None
                source = definition.persistence.migration_source
                assert source is not None
                assert source.package == "ocp_module_analysis_areas"
                assert source.resource == "migrations/history"
                assert source.revision_namespace == "mod_analysis_areas"
                assert source.adopted_revisions == frozenset(ADOPTED_FILES)
                registry = build_persistence_registry(available)

                # #188 will remove the host copies. Model precisely that source
                # split in a temporary Alembic tree without changing host files.
                exclusive_alembic = root / "exclusive-alembic"
                shutil.copytree(host / "backend/alembic", exclusive_alembic)
                for filename in ADOPTED_FILES.values():
                    (exclusive_alembic / "versions" / filename).unlink()

                config = Config(str(host / "backend/alembic.ini"))
                config.set_main_option("script_location", str(exclusive_alembic))
                coordinator = MigrationCoordinator(config, registry)
                plan = coordinator.preflight()
                scripts = ScriptDirectory.from_config(config)
                assert scripts.get_heads() == [EXPECTED_HEAD]
                for revision in ADOPTED_FILES:
                    path = Path(scripts.get_revision(revision).path).resolve()
                    assert path.is_relative_to(history.resolve())
                assert scripts.get_revision("20260819_0032").down_revision == "20260819_0031"
                assert scripts.get_revision("20260822_0033").down_revision == "20260819_0032"
                assert plan[-1].module_id == "host"
                assert plan[-1].revision == EXPECTED_HEAD

                # A database already at the global head performs no upgrade step;
                # in particular none of the adopted revisions can run again.
                class ExistingHeadCoordinator(MigrationCoordinator):
                    async def _current_heads(self) -> tuple[str, ...]:
                        return (EXPECTED_HEAD,)

                existing = ExistingHeadCoordinator(config, registry)
                from app.platform.modules import migrations as migrations_module

                original_upgrade = migrations_module.command.upgrade

                def unexpected_upgrade(*_args, **_kwargs) -> None:
                    raise AssertionError("current-head database must not execute migrations")

                migrations_module.command.upgrade = unexpected_upgrade
                try:
                    existing.upgrade()
                finally:
                    migrations_module.command.upgrade = original_upgrade

                # Until #188 removes the host copies, the real coordinator must
                # reject duplicate source ownership rather than shadowing it.
                duplicate_config = Config(str(host / "backend/alembic.ini"))
                try:
                    MigrationCoordinator(duplicate_config, registry).preflight()
                except ModulePersistenceError as exc:
                    assert "multiple migration sources" in str(exc)
                    assert "20260814_0014" in str(exc)
                else:
                    raise AssertionError("duplicate host/module revisions were accepted")

            assert sys.path == python_path_before
            print(
                "host contract passed: verified and installed disabled; installed-wheel parity; "
                "exclusive adopted-source preflight; existing-head no-op; duplicate fail-fast; "
                f"head={EXPECTED_HEAD}; sha256={verified.bundle_sha256}"
            )
    finally:
        parked_frontend.rename(builtin_frontend)


if __name__ == "__main__":
    main()
