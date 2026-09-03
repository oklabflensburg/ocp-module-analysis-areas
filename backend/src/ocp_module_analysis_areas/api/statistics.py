"""Module-owned translation at the public Statistics SDK boundary."""

import uuid
from dataclasses import asdict

from app.platform.modules.sdk import (
    AreaStatistics,
    AreaStatisticSeries,
    StatisticsArea,
    StatisticsSelection,
)

from .schemas import (
    AnalysisAreaDetail,
    AreaStatisticSeriesRead,
    AreaStatisticsRead,
    StatisticsAreaReference,
)


def statistics_selection(area: AnalysisAreaDetail) -> StatisticsSelection:
    requested = StatisticsArea(
        id=uuid.UUID(area.id),
        slug=area.slug,
        name=area.name,
        area_type=area.area_type,
    )
    target_value = area.parent if area.area_type == "QUARTER" else area
    municipality_value = area if area.area_type == "MUNICIPALITY" else area.municipality
    if target_value is None or municipality_value is None:
        raise ValueError("Analysis area has no complete statistics hierarchy")
    target = StatisticsArea(
        id=uuid.UUID(target_value.id),
        slug=target_value.slug,
        name=target_value.name,
        area_type=target_value.area_type,
    )
    municipality = StatisticsArea(
        id=uuid.UUID(municipality_value.id),
        slug=municipality_value.slug,
        name=municipality_value.name,
        area_type=municipality_value.area_type,
    )
    return StatisticsSelection(
        requested=requested,
        target=target,
        municipality=municipality,
        inherited=requested.id != target.id,
    )


def _area_reference(area: StatisticsArea) -> StatisticsAreaReference:
    """Adapt the SDK-owned UUID identity to this module's string API contract."""
    return StatisticsAreaReference(
        id=str(area.id),
        slug=area.slug,
        name=area.name,
        area_type=area.area_type,
    )


def area_statistics_read(result: AreaStatistics) -> AreaStatisticsRead:
    return AreaStatisticsRead(
        area=_area_reference(result.area),
        statistics_area=_area_reference(result.statistics_area),
        inherited_from_parent=result.inherited_from_parent,
        source=asdict(result.source) if result.source is not None else None,
        latest=[asdict(value) for value in result.latest],
    )


def area_statistic_series_read(result: AreaStatisticSeries) -> AreaStatisticSeriesRead:
    return AreaStatisticSeriesRead(
        area=_area_reference(result.area),
        statistics_area=_area_reference(result.statistics_area),
        inherited_from_parent=result.inherited_from_parent,
        source=asdict(result.source) if result.source is not None else None,
        metric=dict(result.metric),
        series=[asdict(point) for point in result.series],
    )
