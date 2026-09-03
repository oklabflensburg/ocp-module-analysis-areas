from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.platform.modules.sdk import (
    AreaStatistics,
    AreaStatisticSeries,
    StatisticsArea,
    StatisticSeriesPoint,
    StatisticsSource,
    StatisticValue,
)

from ocp_module_analysis_areas.api.statistics import (
    area_statistic_series_read,
    area_statistics_read,
)

REQUESTED_ID = UUID("33333333-3333-4333-8333-333333333333")
TARGET_ID = UUID("22222222-2222-4222-8222-222222222222")


def area(identifier: UUID, slug: str, name: str, area_type: str) -> StatisticsArea:
    return StatisticsArea(id=identifier, slug=slug, name=name, area_type=area_type)


def source() -> StatisticsSource:
    return StatisticsSource(
        name="Population",
        url="https://example.test/statistics",
        license="CC-BY",
        source_updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        last_import_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_statistics_adapter_converts_sdk_uuid_identities_to_api_strings() -> None:
    result = AreaStatistics(
        area=area(REQUESTED_ID, "hafen", "Hafen", "QUARTER"),
        statistics_area=area(TARGET_ID, "nord", "Nord", "DISTRICT"),
        inherited_from_parent=True,
        source=source(),
        latest=(
            StatisticValue(
                key="population",
                name="Population",
                category="Demography",
                value=Decimal(95),
                unit="people",
                period="2025",
                period_start=date(2025, 1, 1),
                area_level="DISTRICT",
                is_calculated=False,
                municipality_value=Decimal(110),
                difference=Decimal(-15),
                relative_difference=Decimal("-13.636"),
            ),
        ),
    )

    response = area_statistics_read(result)

    assert response.area.id == str(REQUESTED_ID)
    assert response.statistics_area.id == str(TARGET_ID)
    assert response.latest[0].value == Decimal(95)
    assert response.source is not None
    assert response.source.source_updated_at == datetime(2026, 7, 1, tzinfo=UTC)


def test_series_adapter_converts_both_sdk_uuid_identities_to_api_strings() -> None:
    result = AreaStatisticSeries(
        area=area(REQUESTED_ID, "hafen", "Hafen", "QUARTER"),
        statistics_area=area(TARGET_ID, "nord", "Nord", "DISTRICT"),
        inherited_from_parent=True,
        source=source(),
        metric={
            "key": "population",
            "name": "Population",
            "unit": "people",
            "category": "Demography",
        },
        series=(StatisticSeriesPoint("2025", date(2025, 1, 1), Decimal(95), False),),
    )

    response = area_statistic_series_read(result)

    assert response.area.id == str(REQUESTED_ID)
    assert response.statistics_area.id == str(TARGET_ID)
    assert response.metric["key"] == "population"
    assert response.series[0].period_start == date(2025, 1, 1)
