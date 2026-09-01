from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

import pytest
from fastapi import HTTPException

try:
    from app.platform.modules.sdk import PolygonScope
except ModuleNotFoundError:
    app_module = ModuleType("app")
    platform_module = ModuleType("app.platform")
    modules_module = ModuleType("app.platform.modules")
    sdk_module = ModuleType("app.platform.modules.sdk")

    class Port:
        pass

    @dataclass(frozen=True, slots=True)
    class PolygonScope:
        polygon_ids: tuple[int, ...]

    @dataclass(frozen=True, slots=True)
    class PolygonFilterValues:
        categories: tuple[str, ...] = ()
        floors: tuple[str, ...] = ()
        area_sizes: tuple[str, ...] = ()
        occupancy_statuses: tuple[str, ...] = ()
        business_structures: tuple[str, ...] = ()
        sources: tuple[str, ...] = ()

    sdk_module.CachePort = Port
    sdk_module.CacheGenerationPort = Port
    sdk_module.DatabaseSessionProvider = Port
    sdk_module.HttpClientFactoryPort = Port
    sdk_module.OsmFeatureSnapshot = Port
    sdk_module.OsmSnapshotQuery = Port
    sdk_module.OsmSnapshotQueryPort = Port
    sdk_module.OsmTagFilter = Port
    sdk_module.PolygonAnalyticsPort = Port
    sdk_module.PolygonFilterValues = PolygonFilterValues
    sdk_module.PolygonQueryPort = Port
    sdk_module.PolygonScope = PolygonScope
    sys.modules.update(
        {
            "app": app_module,
            "app.platform": platform_module,
            "app.platform.modules": modules_module,
            "app.platform.modules.sdk": sdk_module,
        }
    )

from ocp_module_analysis_areas.api.filters import NONE, _values
from ocp_module_analysis_areas.application.cache import (
    cache_key,
    cache_status,
    get_or_compute,
)
from ocp_module_analysis_areas.application.queries import polygon_scope


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.set_calls: list[tuple[str, bytes, int]] = []

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int) -> bool:
        self.values[key] = value
        self.set_calls.append((key, value, ttl_seconds))
        return True


@pytest.mark.asyncio
async def test_module_cache_reports_miss_then_hit_and_preserves_ttl() -> None:
    cache = MemoryCache()
    computations = 0

    async def compute() -> dict[str, list[int]]:
        nonlocal computations
        computations += 1
        return {"items": [1, 2]}

    first = await get_or_compute(cache, "areas:v3:key", ttl_seconds=321, compute=compute)
    assert first == {"items": [1, 2]}
    assert cache_status() == "MISS"
    assert cache.set_calls[0][2] == 321

    second = await get_or_compute(cache, "areas:v3:key", ttl_seconds=321, compute=compute)
    assert second == first
    assert cache_status() == "HIT"
    assert computations == 1


def test_cache_keys_are_relative_stable_and_parameter_sensitive() -> None:
    first = cache_key("analytics", {"area": "one", "filters": ()}, generation="9")
    reordered = cache_key("analytics", {"filters": (), "area": "one"}, generation="9")
    changed = cache_key("analytics", {"area": "two", "filters": ()}, generation="9")
    assert first == reordered
    assert first != changed
    assert first.startswith("analytics:v9:")
    assert "analysis-areas" not in first


class ScalarValues:
    def all(self) -> list[int]:
        return [4, 4, 7]


class ScopeSession:
    async def scalars(self, statement):
        compiled = str(statement)
        assert "polygon_analysis_areas.analysis_area_id" in compiled
        assert "polygon_analysis_areas.polygon_id" in compiled
        return ScalarValues()


@pytest.mark.asyncio
async def test_area_relation_is_materialized_as_unique_immutable_polygon_scope() -> None:
    scope = await polygon_scope(ScopeSession(), 23)
    assert scope == PolygonScope((4, 7))


def test_empty_polygon_scope_is_explicit_not_unbounded() -> None:
    assert PolygonScope(()).polygon_ids == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(["EG,OG", "EG"], ("EG", "OG")), (None, ()), ([NONE], (NONE,))],
)
def test_filter_parser_preserves_csv_repeat_and_none_semantics(raw, expected) -> None:
    assert _values(raw, frozenset({"EG", "OG"}), "floors") == expected


def test_filter_parser_rejects_invalid_and_mixed_none_values() -> None:
    with pytest.raises(HTTPException) as invalid:
        _values(["roof"], frozenset({"EG"}), "floors")
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException) as mixed:
        _values(["NONE,EG"], frozenset({"EG"}), "floors")
    assert mixed.value.detail["error"]["code"] == "INVALID_POLYGON_FILTER"
