"""Real PostgreSQL proof for the external Statistics query service."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.platform.modules.sdk import StatisticsArea, StatisticsSelection
from ocp_module_statistics.application.query_service import SqlStatisticsQueryService
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def statistics_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = get_settings().database_url
    schema = "test_statistics_query_contract"
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except (ConnectionError, DBAPIError, OSError, OperationalError) as exc:
        await admin.dispose()
        pytest.skip(f"PostgreSQL is unavailable: {type(exc).__name__}")
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("""
CREATE TABLE statistical_datasets (
  id integer PRIMARY KEY, name text NOT NULL, source text NOT NULL,
  source_url text NOT NULL, license text NOT NULL,
  last_import_at timestamptz, source_updated_at timestamptz
)
""")
            )
            await connection.execute(
                text("""
CREATE TABLE statistical_metrics (
  id integer PRIMARY KEY, dataset_id integer NOT NULL,
  key text NOT NULL, name text NOT NULL, category text NOT NULL,
  unit text NOT NULL, public boolean NOT NULL
)
""")
            )
            await connection.execute(
                text("""
CREATE TABLE external_area_mappings (
  id integer PRIMARY KEY, source text NOT NULL,
  external_area_name text NOT NULL, level text NOT NULL
)
""")
            )
            await connection.execute(
                text("""
CREATE TABLE statistical_observations (
  id integer PRIMARY KEY, metric_id integer NOT NULL,
  statistical_area_id integer NOT NULL, period_start date NOT NULL,
  value_numeric numeric, value_text text, is_calculated boolean NOT NULL
)
""")
            )
            await connection.execute(
                text("""
INSERT INTO statistical_datasets VALUES
  (1,'Population','sh','https://example.test/statistics','CC-BY',:imported,:updated)
"""),
                {
                    "imported": datetime(2026, 8, 1, tzinfo=UTC),
                    "updated": datetime(2026, 7, 1, tzinfo=UTC),
                },
            )
            await connection.execute(
                text("""
INSERT INTO statistical_metrics VALUES
  (10,1,'population','Population','Demography','people',true)
""")
            )
            await connection.execute(
                text("""
INSERT INTO external_area_mappings VALUES
  (1,'sh','Flensburg','MUNICIPALITY'),
  (2,'sh','Nord','DISTRICT')
""")
            )
            await connection.execute(
                text("""
INSERT INTO statistical_observations VALUES
  (1,10,1,'2024-01-01',100,NULL,false),
  (2,10,1,'2025-01-01',110,NULL,false),
  (3,10,2,'2024-01-01',90,NULL,false),
  (4,10,2,'2025-01-01',95,NULL,false)
""")
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def area(identifier: int, slug: str, name: str, area_type: str) -> StatisticsArea:
    return StatisticsArea(id=identifier, slug=slug, name=name, area_type=area_type)


@pytest.mark.asyncio
async def test_real_statistics_queries_cover_selection_comparison_and_missing_cases(
    statistics_sessions: async_sessionmaker[AsyncSession],
) -> None:
    municipality = area(1, "flensburg", "Flensburg", "MUNICIPALITY")
    district = area(2, "nord", "Nord", "DISTRICT")
    quarter = area(3, "hafen", "Hafen", "QUARTER")
    service = SqlStatisticsQueryService()

    async with statistics_sessions() as session:
        municipality_result = await service.for_selection(
            session,
            StatisticsSelection(municipality, municipality, municipality, False),
        )
        assert municipality_result is not None
        assert municipality_result.latest[0].value == Decimal(110)
        assert municipality_result.latest[0].difference == Decimal(0)

        district_selection = StatisticsSelection(district, district, municipality, False)
        district_result = await service.for_selection(session, district_selection)
        assert district_result is not None
        assert district_result.latest[0].value == Decimal(95)
        assert district_result.latest[0].municipality_value == Decimal(110)
        assert district_result.latest[0].difference == Decimal(-15)
        assert district_result.source is not None

        inherited = await service.for_selection(
            session,
            StatisticsSelection(quarter, district, municipality, True),
        )
        assert inherited is not None
        assert inherited.area == quarter
        assert inherited.statistics_area == district
        assert inherited.inherited_from_parent is True

        series = await service.series_for_selection(session, district_selection, "population")
        assert series is not None
        assert [(point.period_start, point.value) for point in series.series] == [
            (date(2024, 1, 1), Decimal(90)),
            (date(2025, 1, 1), Decimal(95)),
        ]
        assert await service.series_for_selection(session, district_selection, "missing") is None
        unmapped = area(4, "unknown", "Unknown", "DISTRICT")
        assert (
            await service.for_selection(
                session,
                StatisticsSelection(unmapped, unmapped, municipality, False),
            )
            is None
        )

        assert await session.scalar(text("SELECT count(*) FROM statistical_observations")) == 4
        assert not session.in_transaction() or not session.dirty
