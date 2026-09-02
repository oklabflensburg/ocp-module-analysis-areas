from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

ADOPTED_FILES = {
    "20260814_0014": "20260814_0014_analysis_areas.py",
    "20260817_0023": "20260817_0023_area_wikidata.py",
    "20260818_0025": "20260818_0025_osm_external_links.py",
    "20260819_0032": "20260819_0032_optimize_area_poi_analytics.py",
}
EXPECTED_HEAD = "20260901_0035"
EXPECTED_GRAPH_HEAD = "mod_reference_20260901_0002"
CUTOVER_ENV = ""


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **environment},
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"Command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def copy_cutover_host(host: Path, destination: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".env",
        ".venv",
        "node_modules",
        ".nuxt",
        ".output",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    )
    shutil.copytree(host / "backend", destination / "backend", ignore=ignored)
    shutil.copytree(host / "frontend", destination / "frontend", ignore=ignored)
    # pnpm rejects a project whose node_modules resolves outside its root. A
    # hard-linked test copy keeps the pinned dependency tree local and cheap.
    shutil.copytree(
        host / "frontend/node_modules",
        destination / "frontend/node_modules",
        copy_function=os.link,
        symlinks=True,
    )
    for filename in ADOPTED_FILES.values():
        (destination / "backend/alembic/versions" / filename).unlink()


def cli(
    python: Path,
    backend: Path,
    install_root: Path,
    environment: Mapping[str, str],
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        (
            str(python),
            "-m",
            "app.cli.modules",
            "--root",
            str(install_root),
            *arguments,
        ),
        cwd=backend,
        environment=environment,
        check=check,
    )


def generated_environment(
    python: Path,
    backend: Path,
    install_root: Path,
    environment: Mapping[str, str],
) -> dict[str, str]:
    result = cli(
        python,
        backend,
        install_root,
        environment,
        "env",
        "--format",
        "json",
    )
    values = json.loads(result.stdout)
    expected_keys = {
        "ENABLED_MODULES",
        "OCP_BACKEND_MODULES",
        "OCP_ENABLED_INSTALLED_BACKEND_PATHS",
        "OCP_EXCLUDED_BUILTIN_MODULES",
        "OCP_FRONTEND_MODULES",
        "OCP_INSTALLED_FRONTEND_MODULE_ROOTS",
    }
    assert set(values) == expected_keys
    return values


def assert_failed(result: subprocess.CompletedProcess[str], expected: str) -> None:
    assert result.returncode != 0
    output = f"{result.stdout}\n{result.stderr}"
    assert expected in output, output


def json_output(result: subprocess.CompletedProcess[str]) -> dict:
    lines = (line for line in result.stdout.splitlines() if line.startswith("{"))
    return json.loads(next(lines))


def frontend_check(frontend: Path, environment: Mapping[str, str]) -> str:
    result = run(
        ("pnpm", "modules:check"),
        cwd=frontend,
        environment=environment,
    )
    return result.stdout


def backend_runtime_check(
    python: Path, backend: Path, environment: Mapping[str, str]
) -> None:
    probe = """
import asyncio
from datetime import UTC, datetime
from app.core.config import get_settings
from app.main import app, event_bus, module_runtime
from app.platform.modules import EntryPointModuleDiscovery, FirstPartyModuleDiscovery
from app.platform.modules.runtime import resolve_module_definitions
from app.platform.modules.sdk import (
    OSM_POSTPROCESSING_COMPLETED_EVENT,
    OSM_SNAPSHOT_QUERY_SERVICE_ID,
    OSM_SNAPSHOT_QUERY_SERVICE_VERSION,
    POLYGON_IDENTITY_SERVICE_ID,
    POLYGON_IDENTITY_SERVICE_VERSION,
    POLYGON_SPATIAL_MATCH_SERVICE_ID,
    POLYGON_SPATIAL_MATCH_SERVICE_VERSION,
    STATISTICS_QUERY_SERVICE_ID,
    STATISTICS_QUERY_SERVICE_VERSION,
    OsmSnapshotQueryPort,
    OsmPostprocessingCompleted,
    PolygonSpatialMatchPort,
    PolygonIdentityPort,
    StatisticsQueryPort,
    event_envelope,
)
from ocp_module_analysis_areas.contracts import (
    SERVICE_ID,
    SERVICE_VERSION,
    WIKIDATA_MAINTENANCE_SERVICE_ID,
    WIKIDATA_MAINTENANCE_SERVICE_VERSION,
    AnalysisAreaQueryService,
    WikidataMaintenanceService,
)
from ocp_module_analysis_areas.application.osm_sync import OsmAnalysisAreaSync

osm_event_calls = []
async def contract_osm_sync(self):
    osm_event_calls.append(self)
OsmAnalysisAreaSync.sync = contract_osm_sync

settings = get_settings()
definitions = resolve_module_definitions(
    enabled_module_ids=settings.enabled_module_list,
    discovery_providers=(FirstPartyModuleDiscovery(), EntryPointModuleDiscovery()),
    host_version=settings.api_version,
)
analysis = [item for item in definitions if item[1].id == "analysis-areas"]
assert len(analysis) == 1
assert analysis[0][0].origin.startswith("entry-point:analysis-areas=")
assert "analysis-areas.wikidata-maintenance" in analysis[0][1].capabilities
assert not any(
    item.declared_id == "analysis-areas"
    for item in FirstPartyModuleDiscovery().discover_available()
)
paths = set(app.openapi()["paths"])
for expected in (
    "/api/v1/analysis-areas",
    "/api/v1/analysis-areas/geojson",
    "/api/v1/analysis-areas/by-slug/{slug}",
    "/api/v1/analysis-areas/{area_id}",
):
    assert expected in paths, expected
assert module_runtime.job_registry is not None
assert "analysis-areas.wikidata-refresh" in {
    item.job_id for item in module_runtime.job_registry.jobs
}
services = module_runtime.registry.get("analysis-areas").context.services
assert services is not None
assert services.optional(
    AnalysisAreaQueryService, service_id=SERVICE_ID, version=SERVICE_VERSION
) is not None
assert services.optional(
    WikidataMaintenanceService,
    service_id=WIKIDATA_MAINTENANCE_SERVICE_ID,
    version=WIKIDATA_MAINTENANCE_SERVICE_VERSION,
) is not None
assert services.require(
    OsmSnapshotQueryPort,
    service_id=OSM_SNAPSHOT_QUERY_SERVICE_ID,
    version=OSM_SNAPSHOT_QUERY_SERVICE_VERSION,
) is not None
assert services.require(
    PolygonSpatialMatchPort,
    service_id=POLYGON_SPATIAL_MATCH_SERVICE_ID,
    version=POLYGON_SPATIAL_MATCH_SERVICE_VERSION,
) is not None
assert services.require(
    PolygonIdentityPort,
    service_id=POLYGON_IDENTITY_SERVICE_ID,
    version=POLYGON_IDENTITY_SERVICE_VERSION,
) is not None
assert services.require(
    StatisticsQueryPort,
    service_id=STATISTICS_QUERY_SERVICE_ID,
    version=STATISTICS_QUERY_SERVICE_VERSION,
) is not None
subscription = event_bus.subscription("analysis-areas.sync-after-osm-postprocessing")
assert subscription is not None
assert subscription.event_name == OSM_POSTPROCESSING_COMPLETED_EVENT
assert subscription.versions == frozenset({1})
asyncio.run(event_bus.dispatch(event_envelope(OsmPostprocessingCompleted(
    sequence=123,
    osm_timestamp=datetime(2026, 9, 1, tzinfo=UTC),
    inserted=1,
    updated=2,
    deleted=3,
))))
assert len(osm_event_calls) == 1
"""
    run((str(python), "-c", probe), cwd=backend, environment=environment)


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    host = Path(sys.argv[1]).resolve()
    bundle = Path(sys.argv[2]).resolve()
    statistics_bundle = Path(sys.argv[3]).resolve()
    contract = json.loads(
        (repository / ".github/ocp-host-contract.json").read_text(encoding="utf-8")
    )
    expected = contract["commit"]
    actual = run(("git", "rev-parse", "HEAD"), cwd=host, environment={}).stdout.strip()
    if actual != expected:
        raise SystemExit(f"Host contract mismatch: expected {expected}, got {actual}")

    # Set the one shared composition input before the host reads settings or discovery.
    os.environ.update(
        {
            "ENABLED_MODULES": "",
            "OCP_ENABLED_INSTALLED_BACKEND_PATHS": "",
            "OCP_EXCLUDED_BUILTIN_MODULES": CUTOVER_ENV,
            "OCP_FRONTEND_MODULES": "",
            "OCP_INSTALLED_FRONTEND_MODULE_ROOTS": "",
        }
    )
    os.chdir(host / "backend")

    from alembic.config import Config
    from alembic.script import ScriptDirectory
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

    host_versions = host / "backend/alembic/versions"
    bundle_python = host / "backend/.venv/bin/python"
    with TemporaryDirectory(
        prefix=".ocp-analysis-areas-contract-", dir=repository
    ) as temporary:
        root = Path(temporary)
        cutover_host = root / "host"
        copy_cutover_host(host, cutover_host)
        cutover_backend = cutover_host / "backend"
        cutover_frontend = cutover_host / "frontend"
        builtin_detail_map = (
            cutover_frontend
            / "app/components/analysis/AnalysisAreaDetailMap.vue"
        )
        builtin_detail_map.unlink(missing_ok=True)
        assert not builtin_detail_map.exists()
        install_root = root / "modules"
        base_environment = {
            "ENABLED_MODULES": "",
            "OCP_ENABLED_INSTALLED_BACKEND_PATHS": "",
            "OCP_EXCLUDED_BUILTIN_MODULES": CUTOVER_ENV,
            "OCP_FRONTEND_MODULES": "",
            "OCP_INSTALLED_FRONTEND_MODULE_ROOTS": "",
            "OCP_MODULE_INSTALL_ROOT": str(install_root),
        }

        verified = cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "verify",
            str(bundle),
        )
        verified_package = json_output(verified)
        with staged_ocp_bundle(bundle) as (_package_root, package):
            assert verified_package["bundle_sha256"] == package.bundle_sha256

        installed_result = cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "install",
            str(bundle),
        )
        installed = json_output(installed_result)
        assert installed["enabled"] is False
        statistics_installed = json_output(
            cli(
                bundle_python,
                cutover_backend,
                install_root,
                base_environment,
                "install",
                str(statistics_bundle),
            )
        )
        assert statistics_installed["id"] == "statistics"
        assert statistics_installed["enabled"] is False
        disabled_environment = generated_environment(
            bundle_python, cutover_backend, install_root, base_environment
        )
        assert disabled_environment["OCP_EXCLUDED_BUILTIN_MODULES"] == CUTOVER_ENV
        assert disabled_environment["OCP_ENABLED_INSTALLED_BACKEND_PATHS"] == ""
        assert disabled_environment["OCP_FRONTEND_MODULES"] == ""
        assert disabled_environment["OCP_INSTALLED_FRONTEND_MODULE_ROOTS"]
        assert "no optional modules enabled" in frontend_check(
            cutover_frontend, {**base_environment, **disabled_environment}
        )

        installed_paths = installed_backend_distribution_paths(install_root)
        assert len(installed_paths) == 2
        analysis_path = next(
            path for path in installed_paths if (path / "ocp_module_analysis_areas").is_dir()
        )
        statistics_path = next(
            path for path in installed_paths if (path / "ocp_module_statistics").is_dir()
        )
        run(
            (
                str(bundle_python),
                str(host / "scripts/check_external_module_imports.py"),
                str(analysis_path / "ocp_module_analysis_areas"),
            ),
            cwd=cutover_backend,
            environment=base_environment,
        )
        run(
            (
                str(bundle_python),
                str(host / "scripts/check_external_module_imports.py"),
                str(statistics_path / "ocp_module_statistics"),
            ),
            cwd=cutover_backend,
            environment=base_environment,
        )
        history = analysis_path / "ocp_module_analysis_areas/migrations/history"
        assert {path.name for path in history.glob("*.py")} == {
            "__init__.py",
            *ADOPTED_FILES.values(),
        }
        for filename in ADOPTED_FILES.values():
            assert (history / filename).read_bytes() == (host_versions / filename).read_bytes()

        # Disabled installation still participates in passive migration discovery.
        passive = run(
            (str(bundle_python), "-m", "app.cli.module_migrations", "preflight"),
            cwd=cutover_backend,
            environment={**base_environment, **disabled_environment},
        )
        assert f"host: {EXPECTED_HEAD}" in passive.stdout

        python_path_before = sys.path.copy()
        with scoped_module_python_paths(installed_paths):
            available = resolve_available_persistence_definitions(
                (FirstPartyModuleDiscovery(), EntryPointModuleDiscovery())
            )
            analysis = [item for item in available if item[1].id == "analysis-areas"]
            assert len(analysis) == 1
            definition, manifest = analysis[0]
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

            exclusive_config = Config(str(cutover_backend / "alembic.ini"))
            exclusive_config.set_main_option(
                "script_location", str(cutover_backend / "alembic")
            )
            coordinator = MigrationCoordinator(exclusive_config, registry)
            plan = coordinator.preflight()
            scripts = ScriptDirectory.from_config(exclusive_config)
            assert scripts.get_heads() == [EXPECTED_GRAPH_HEAD]
            for revision in ADOPTED_FILES:
                path = Path(scripts.get_revision(revision).path).resolve()
                assert path.is_relative_to(history.resolve())
            assert scripts.get_revision("20260819_0032").down_revision == "20260819_0031"
            assert scripts.get_revision("20260822_0033").down_revision == "20260819_0032"
            assert any(
                step.module_id == "host" and step.revision == EXPECTED_HEAD
                for step in plan
            )

            # A database already at the complete graph head must not replay any
            # adopted historical revision.
            class ExistingHeadCoordinator(MigrationCoordinator):
                async def _current_heads(self) -> tuple[str, ...]:
                    return (EXPECTED_GRAPH_HEAD,)

            from app.platform.modules import migrations as migrations_module

            existing = ExistingHeadCoordinator(exclusive_config, registry)
            original_upgrade = migrations_module.command.upgrade

            def unexpected_upgrade(*_args, **_kwargs) -> None:
                raise AssertionError("current-head database must not execute migrations")

            migrations_module.command.upgrade = unexpected_upgrade
            try:
                existing.upgrade()
            finally:
                migrations_module.command.upgrade = original_upgrade

            duplicate_config = Config(str(host / "backend/alembic.ini"))
            try:
                MigrationCoordinator(duplicate_config, registry).preflight()
            except ModulePersistenceError as exc:
                assert "multiple migration sources" in str(exc)
                assert "20260814_0014" in str(exc)
            else:
                raise AssertionError("duplicate host/module revisions were accepted")
        assert sys.path == python_path_before

        cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "enable",
            "statistics",
        )
        cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "enable",
            "analysis-areas",
        )
        enabled_environment = generated_environment(
            bundle_python, cutover_backend, install_root, base_environment
        )
        assert set(enabled_environment["ENABLED_MODULES"].split(",")) == {
            "analysis-areas",
            "statistics",
        }
        assert set(enabled_environment["OCP_FRONTEND_MODULES"].split(",")) == {
            "analysis-areas",
            "statistics",
        }
        assert "site-packages" in enabled_environment[
            "OCP_ENABLED_INSTALLED_BACKEND_PATHS"
        ]
        assert enabled_environment["OCP_INSTALLED_FRONTEND_MODULE_ROOTS"]
        assert enabled_environment["OCP_EXCLUDED_BUILTIN_MODULES"] == CUTOVER_ENV
        enabled = {**base_environment, **enabled_environment}

        dependency_failure = cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "disable",
            "statistics",
            check=False,
        )
        assert_failed(dependency_failure, "analysis-areas")

        backend_runtime_check(bundle_python, cutover_backend, enabled)
        sync_contract = run(
            (
                str(bundle_python),
                "-m",
                "pytest",
                str(
                    repository
                    / "tests/host-baseline/backend/tests/test_analysis_areas_characterization.py"
                ),
                str(
                    repository
                    / "tests/host-baseline/backend/tests/test_sync_sdk_113_contract.py"
                ),
                "-q",
            ),
            cwd=cutover_backend,
            environment=enabled,
        )
        # Two characterization tests and two real PostGIS sync tests must run.
        assert "skipped" not in sync_contract.stdout, sync_contract.stdout
        assert "4 passed" in sync_contract.stdout, sync_contract.stdout
        frontend_output = frontend_check(cutover_frontend, enabled)
        assert "analysis-areas" in frontend_output
        assert (cutover_frontend / "frontend-modules/analysis-areas/module.json").is_file()
        installed_frontend_root = Path(
            enabled_environment["OCP_INSTALLED_FRONTEND_MODULE_ROOTS"]
        )
        assert (installed_frontend_root / "analysis-areas/module.json").is_file()
        installed_detail_map = (
            installed_frontend_root
            / "analysis-areas/layer/app/components/analysis/AnalysisAreaDetailMap.vue"
        )
        assert installed_detail_map.is_file()
        installed_detail_route = (
            installed_frontend_root
            / "analysis-areas/layer/app/pages/gebiete/[slug].vue"
        ).read_text(encoding="utf-8")
        assert "../../components/analysis/AnalysisAreaDetailMap.vue" in installed_detail_route
        assert "@ready=\"mapReady = true\"" in installed_detail_route
        assert "data-social-preview-ready" in installed_detail_route

        run(("pnpm", "typecheck"), cwd=cutover_frontend, environment=enabled)
        run(("pnpm", "build"), cwd=cutover_frontend, environment=enabled)

        cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "disable",
            "analysis-areas",
        )
        after_disable = generated_environment(
            bundle_python, cutover_backend, install_root, base_environment
        )
        assert after_disable["ENABLED_MODULES"] == "statistics"
        assert after_disable["OCP_BACKEND_MODULES"] == "statistics"
        assert after_disable["OCP_FRONTEND_MODULES"] == "statistics"
        assert after_disable["OCP_INSTALLED_FRONTEND_MODULE_ROOTS"]
        assert after_disable["OCP_EXCLUDED_BUILTIN_MODULES"] == CUTOVER_ENV
        assert "statistics" in frontend_check(
            cutover_frontend, {**base_environment, **after_disable}
        )
        disabled_passive = run(
            (str(bundle_python), "-m", "app.cli.module_migrations", "preflight"),
            cwd=cutover_backend,
            environment={**base_environment, **after_disable},
        )
        assert f"host: {EXPECTED_HEAD}" in disabled_passive.stdout

        cli(
            bundle_python,
            cutover_backend,
            install_root,
            base_environment,
            "enable",
            "analysis-areas",
        )
        reenabled_environment = generated_environment(
            bundle_python, cutover_backend, install_root, base_environment
        )
        assert reenabled_environment == enabled_environment
        backend_runtime_check(
            bundle_python,
            cutover_backend,
            {**base_environment, **reenabled_environment},
        )
        assert "analysis-areas" in frontend_check(
            cutover_frontend, {**base_environment, **reenabled_environment}
        )

        print(
            "host contract passed: normal verify/install disabled; passive migrations; "
            "installed-package import guards; Statistics dependency fail-fast; "
            "exclusive ownership; normal CLI enable/disable/re-enable; "
            "wikidata job/service/capability present; OSM/polygon/Statistics services resolved; "
            "OSM subscriber dispatched; real PostGIS spatial-match/identity/relation/"
            "upsert/generation chain; "
            "backend/API characterization and frontend route/map discovery; "
            "built-in-free detail-map ownership and social-preview ready wiring; "
            "modules:check; typecheck; build; "
            f"head={EXPECTED_HEAD}; sha256={verified_package['bundle_sha256']}"
        )


if __name__ == "__main__":
    main()
