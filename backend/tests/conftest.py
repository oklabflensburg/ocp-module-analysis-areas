"""Small public-SDK stand-in for standalone unit tests.

The real SDK is exercised by scripts/host-contract-test against the pinned Host.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

try:
    import app.platform.modules.sdk  # noqa: F401
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

    @dataclass(frozen=True, slots=True)
    class OsmFeatureCursor:
        osm_type: str
        osm_id: int

    @dataclass(frozen=True, slots=True)
    class OsmTagFilter:
        key: str
        values: tuple[str, ...] = ()

    @dataclass(frozen=True, slots=True)
    class OsmSnapshotQuery:
        osm_types: tuple[str, ...] = ()
        geometry_kinds: tuple[str, ...] = ()
        required_tag_keys: tuple[str, ...] = ()
        tag_filters: tuple[OsmTagFilter, ...] = ()
        bbox: tuple[float, float, float, float] | None = None
        cursor: OsmFeatureCursor | None = None
        limit: int = 100

    @dataclass(frozen=True, slots=True)
    class OsmFeatureSnapshot:
        osm_type: str
        osm_id: int
        tags: dict[str, str]
        geometry_wkb: bytes
        bbox: tuple[float, float, float, float]
        imported_at: object

    @dataclass(frozen=True, slots=True)
    class OsmFeatureSnapshotPage:
        items: tuple[OsmFeatureSnapshot, ...]
        next_cursor: OsmFeatureCursor | None = None

    for name in (
        "CachePort",
        "CacheGenerationPort",
        "DatabaseSessionProvider",
        "HttpClientFactoryPort",
        "OsmSnapshotQueryPort",
        "PolygonAnalyticsPort",
        "PolygonQueryPort",
    ):
        setattr(sdk_module, name, Port)
    sdk_module.OsmFeatureCursor = OsmFeatureCursor
    sdk_module.OsmFeatureSnapshot = OsmFeatureSnapshot
    sdk_module.OsmFeatureSnapshotPage = OsmFeatureSnapshotPage
    sdk_module.OsmSnapshotQuery = OsmSnapshotQuery
    sdk_module.OsmTagFilter = OsmTagFilter
    sdk_module.PolygonFilterValues = PolygonFilterValues
    sdk_module.PolygonScope = PolygonScope
    sys.modules.update(
        {
            "app": app_module,
            "app.platform": platform_module,
            "app.platform.modules": modules_module,
            "app.platform.modules.sdk": sdk_module,
        }
    )
