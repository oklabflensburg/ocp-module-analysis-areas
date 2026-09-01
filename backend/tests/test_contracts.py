from __future__ import annotations

import ast
import json
import re
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "backend/src/ocp_module_analysis_areas"

EXPECTED_ROUTES = {
    "",
    "/geojson",
    "/sitemap",
    "/by-slug/{slug}",
    "/by-slug/{slug}/preview.webp",
    "/by-slug/{slug}/polygons",
    "/by-slug/{slug}/statistics",
    "/by-slug/{slug}/statistics/{metric_key}",
    "/by-slug/{slug}/analytics",
    "/by-slug/{slug}/comparison",
    "/{area_id}",
    "/{area_id}/analytics",
    "/{area_id}/comparison",
}

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_manifest_and_package_versions_are_consistent() -> None:
    manifest = yaml.safe_load((ROOT / "module.yaml").read_text(encoding="utf-8"))
    pyproject = (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    frontend = json.loads((ROOT / "frontend/module.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert manifest["id"] == frontend["id"] == frontend["backendModuleId"] == "analysis-areas"
    assert manifest["version"] == frontend["version"] == package["version"] == "1.2.0"
    assert 'name = "ocp-module-analysis-areas"' in pyproject
    assert 'version = "1.2.0"' in pyproject
    assert manifest["backend"]["package"] == "ocp-module-analysis-areas"
    assert manifest["frontend"]["package"] == "@open-city-planner/analysis-areas"
    assert manifest["requires"]["sdk"] == ">=1.12.0,<2.0.0"
    assert manifest["persistence"]["migrations"] is True
    assert manifest["capabilities"] == [
        "analysis-areas.public-api",
        "analysis-areas.lookup",
        "analysis-areas.geojson",
        "analysis-areas.wikidata-maintenance",
    ]


def test_wikidata_mutations_are_public_and_transactionally_invalidated() -> None:
    module_source = (PACKAGE / "module.py").read_text(encoding="utf-8")
    contracts_source = (PACKAGE / "contracts/__init__.py").read_text(encoding="utf-8")
    application_source = (PACKAGE / "application/wikidata.py").read_text(encoding="utf-8")

    assert "analysis-areas.wikidata-refresh" in module_source
    assert "analysis-areas.wikidata-maintenance" in contracts_source
    assert "context.http" in module_source
    assert "cache_generations.bump" in application_source
    assert "class WikidataMaintenanceService(Protocol)" in contracts_source
    assert "class WikidataSyncResult" in contracts_source
    assert "class WikidataEnrichmentService" in application_source
    assert "async def sync(" in application_source
    assert "async def set_manual_match(" in application_source


def test_host_contract_is_exact_sdk_1_12_merge() -> None:
    contract = json.loads(
        (ROOT / ".github/ocp-host-contract.json").read_text(encoding="utf-8")
    )
    assert contract == {
        "repository": "https://github.com/oklabflensburg/open-city-planner.git",
        "commit": "e1d7921698bb030f9e01de9ad16a9d85cb334b26",
        "source_branch": "staging/epic-91-modular-host",
        "sdk_version": "1.12.0",
        "host_version": "0.2.0",
    }


def test_api_route_inventory_is_unchanged() -> None:
    source = (PACKAGE / "api/router.py").read_text(encoding="utf-8")
    actual = set(re.findall(r"@router\.get\(\s*[\"']([^\"']*)", source))
    assert actual == EXPECTED_ROUTES
    assert 'APIRouter(prefix="/analysis-areas"' in source
    assert 'prefix="/api/v1"' in (PACKAGE / "module.py").read_text(encoding="utf-8")


def test_installable_package_only_imports_the_public_host_sdk() -> None:
    for source in PACKAGE.rglob("*.py"):
        app_imports = {name for name in _imports(source) if name == "app" or name.startswith("app.")}
        assert app_imports <= {"app.platform.modules.sdk"}, (source, app_imports)
    assert not (PACKAGE / "integrations/legacy.py").exists()
    assert not (PACKAGE / "application/legacy_sync.py").exists()


def test_runtime_has_no_direct_provider_or_foreign_domain_access() -> None:
    runtime_sources = [
        source
        for source in PACKAGE.rglob("*.py")
        if "migrations/history" not in source.as_posix()
    ]
    combined = "\n".join(source.read_text(encoding="utf-8") for source in runtime_sources)
    assert "import httpx" not in combined
    assert not re.search(r"\b(?:FROM|JOIN|UPDATE|INTO|DELETE FROM)\s+osm_features\b", combined)
    assert not re.search(r"\b(?:FROM|JOIN|UPDATE|INTO|DELETE FROM)\s+user_polygons\b", combined)


def test_historical_revision_ids_and_chain_links_are_immutable() -> None:
    expected = {
        "20260814_0014_analysis_areas.py": ("20260814_0014", "20260814_0013"),
        "20260817_0023_area_wikidata.py": ("20260817_0023", "20260817_0022"),
        "20260818_0025_osm_external_links.py": ("20260818_0025", "20260818_0024"),
        "20260819_0032_optimize_area_poi_analytics.py": ("20260819_0032", "20260819_0031"),
    }
    history = PACKAGE / "migrations/history"
    assert {path.name for path in history.glob("*.py")} == {"__init__.py", *expected}
    for filename, (revision, down_revision) in expected.items():
        source = (history / filename).read_text(encoding="utf-8")
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(source, filename=filename).body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id
            in {"revision", "down_revision", "branch_labels", "depends_on"}
        }
        assert assignments == {
            "revision": revision,
            "down_revision": down_revision,
            "branch_labels": None,
            "depends_on": None,
        }
    assert '"analysis_areas"' in (history / "20260814_0014_analysis_areas.py").read_text()
    assert 'Geometry("MULTIPOLYGON", srid=4326' in (history / "20260814_0014_analysis_areas.py").read_text()


def test_built_wheel_has_one_namespace_entry_point_and_migrations() -> None:
    wheels = list((ROOT / "backend/dist").glob("*.whl"))
    if not wheels:
        return
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        roots = {name.split("/", 1)[0] for name in names}
        assert roots == {
            "ocp_module_analysis_areas",
            "ocp_module_analysis_areas-1.2.0.dist-info",
        }
        entry_points = archive.read(
            "ocp_module_analysis_areas-1.2.0.dist-info/entry_points.txt"
        ).decode()
        assert "[open_city_planner.modules]" in entry_points
        assert "analysis-areas = ocp_module_analysis_areas.module:DEFINITION" in entry_points
        for revision in (
            "20260814_0014",
            "20260817_0023",
            "20260818_0025",
            "20260819_0032",
        ):
            assert sum(f"migrations/history/{revision}" in name for name in names) == 1
        assert not any("/tests/" in name for name in names)
        assert not any("legacy" in name for name in names)


def test_persistence_definition_declares_exact_historical_adoption() -> None:
    tree = ast.parse((PACKAGE / "module.py").read_text(encoding="utf-8"))
    migration_sources = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ModuleMigrationSource"
    ]
    assert len(migration_sources) == 1
    keywords = {keyword.arg: keyword.value for keyword in migration_sources[0].keywords}
    assert ast.literal_eval(keywords["package"]) == "ocp_module_analysis_areas"
    assert ast.literal_eval(keywords["resource"]) == "migrations/history"
    assert ast.literal_eval(keywords["revision_namespace"]) == "mod_analysis_areas"
    adopted_call = keywords["adopted_revisions"]
    assert isinstance(adopted_call, ast.Call)
    assert ast.literal_eval(adopted_call.args[0]) == {
        "20260814_0014",
        "20260817_0023",
        "20260818_0025",
        "20260819_0032",
    }
