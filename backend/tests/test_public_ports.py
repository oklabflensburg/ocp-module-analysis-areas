from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.platform.modules.sdk import CountValue, PolygonScope
from fastapi import HTTPException

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


def test_sdk_count_values_keep_existing_industry_shape() -> None:
    value = CountValue(key="fashion", count=3, label=None)
    mapped = SimpleNamespace(category=value.key, count=value.count)
    assert vars(mapped) == {"category": "fashion", "count": 3}
