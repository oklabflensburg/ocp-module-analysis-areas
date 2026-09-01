"""Module-owned translation from area hierarchy to the neutral statistics port."""

import uuid

from app.platform.modules.sdk import StatisticsArea, StatisticsSelection

from .schemas import AnalysisAreaDetail


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
