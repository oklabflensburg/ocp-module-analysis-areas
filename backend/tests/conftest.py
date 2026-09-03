"""Small public-SDK stand-in for standalone unit tests.

The real SDK is exercised by scripts/host-contract-test against the pinned Host.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, ModuleType
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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

    @dataclass(frozen=True, slots=True)
    class StatisticsSource:
        name: str
        url: str
        license: str
        source_updated_at: datetime | None
        last_import_at: datetime | None

    @dataclass(frozen=True, slots=True)
    class StatisticValue:
        key: str
        name: str
        category: str
        value: Decimal | None
        unit: str
        period: str
        period_start: date
        area_level: str
        is_calculated: bool
        municipality_value: Decimal | None = None
        difference: Decimal | None = None
        relative_difference: Decimal | None = None

    @dataclass(frozen=True, slots=True)
    class AreaStatistics:
        area: StatisticsArea
        statistics_area: StatisticsArea
        inherited_from_parent: bool
        source: StatisticsSource | None
        latest: tuple[StatisticValue, ...] = ()

    @dataclass(frozen=True, slots=True)
    class StatisticSeriesPoint:
        period: str
        period_start: date
        value: Decimal | None
        suppressed: bool

    @dataclass(frozen=True, slots=True)
    class AreaStatisticSeries:
        area: StatisticsArea
        statistics_area: StatisticsArea
        inherited_from_parent: bool
        source: StatisticsSource | None
        metric: Mapping[str, str]
        series: tuple[StatisticSeriesPoint, ...] = ()

        def __post_init__(self) -> None:
            object.__setattr__(self, "metric", MappingProxyType(dict(self.metric)))

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
        "StatisticsQueryPort",
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
    sdk_module.StatisticsSource = StatisticsSource
    sdk_module.StatisticValue = StatisticValue
    sdk_module.AreaStatistics = AreaStatistics
    sdk_module.StatisticSeriesPoint = StatisticSeriesPoint
    sdk_module.AreaStatisticSeries = AreaStatisticSeries
    sdk_module.STATISTICS_QUERY_SERVICE_ID = "statistics.query"
    sdk_module.STATISTICS_QUERY_SERVICE_VERSION = 1
    sys.modules.update(
        {
            "app": app_module,
            "app.platform": platform_module,
            "app.platform.modules": modules_module,
            "app.platform.modules.sdk": sdk_module,
        }
    )
