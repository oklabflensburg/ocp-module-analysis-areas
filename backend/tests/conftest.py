"""Small public-SDK stand-in for standalone unit tests.

The real SDK is exercised by scripts/host-contract-test against the pinned Host.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from uuid import UUID

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

    @dataclass(frozen=True, slots=True)
    class PolygonSpatialArea:
        external_id: str
        selection_group: str
        geometry_wkb: bytes

    @dataclass(frozen=True, slots=True)
    class PolygonSpatialMatchRequest:
        areas: tuple[PolygonSpatialArea, ...]

    @dataclass(frozen=True, slots=True)
    class PolygonSpatialMatch:
        polygon_id: str
        external_area_id: str
        selection_group: str
        overlap_ratio: float | None

    @dataclass(frozen=True, slots=True)
    class PolygonSpatialMatchResult:
        matches: tuple[PolygonSpatialMatch, ...]

    @dataclass(frozen=True, slots=True)
    class PolygonIdentity:
        id: int
        uuid: UUID

    @dataclass(frozen=True, slots=True)
    class PolygonIdentityRequest:
        polygon_uuids: tuple[UUID, ...]

    @dataclass(frozen=True, slots=True)
    class PolygonIdentityResult:
        resolved: tuple[PolygonIdentity, ...]
        missing: tuple[UUID, ...]

    @dataclass(frozen=True, slots=True)
    class StatisticsArea:
        id: UUID
        slug: str
        name: str
        area_type: str

    @dataclass(frozen=True, slots=True)
    class StatisticsSelection:
        requested: StatisticsArea
        target: StatisticsArea
        municipality: StatisticsArea
        inherited: bool = False

    for name in (
        "CachePort",
        "CacheGenerationPort",
        "DatabaseSessionProvider",
        "HttpClientFactoryPort",
        "OsmSnapshotQueryPort",
        "PolygonAnalyticsPort",
        "PolygonIdentityPort",
        "PolygonQueryPort",
        "PolygonSpatialMatchPort",
    ):
        setattr(sdk_module, name, Port)
    sdk_module.OsmFeatureCursor = OsmFeatureCursor
    sdk_module.OsmFeatureSnapshot = OsmFeatureSnapshot
    sdk_module.OsmFeatureSnapshotPage = OsmFeatureSnapshotPage
    sdk_module.OsmSnapshotQuery = OsmSnapshotQuery
    sdk_module.OsmTagFilter = OsmTagFilter
    sdk_module.PolygonFilterValues = PolygonFilterValues
    sdk_module.PolygonIdentity = PolygonIdentity
    sdk_module.PolygonIdentityRequest = PolygonIdentityRequest
    sdk_module.PolygonIdentityResult = PolygonIdentityResult
    sdk_module.PolygonScope = PolygonScope
    sdk_module.PolygonSpatialArea = PolygonSpatialArea
    sdk_module.PolygonSpatialMatch = PolygonSpatialMatch
    sdk_module.PolygonSpatialMatchRequest = PolygonSpatialMatchRequest
    sdk_module.PolygonSpatialMatchResult = PolygonSpatialMatchResult
    sdk_module.StatisticsArea = StatisticsArea
    sdk_module.StatisticsSelection = StatisticsSelection
    sys.modules.update(
        {
            "app": app_module,
            "app.platform": platform_module,
            "app.platform.modules": modules_module,
            "app.platform.modules.sdk": sdk_module,
        }
    )
