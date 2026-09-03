"""Real PostgreSQL proof for the external Statistics query service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.platform.modules.sdk import (
    PublicQueryLimits,
    StatisticsArea,
    StatisticsSelection,
)
from fastapi import FastAPI
from ocp_module_analysis_areas.api.router import create_router
from ocp_module_analysis_areas.settings import AnalysisAreasSettings
from ocp_module_statistics.application.query_service import SqlStatisticsQueryService
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

MUNICIPALITY_ID = UUID("11111111-1111-4111-8111-111111111111")
DISTRICT_ID = UUID("22222222-2222-4222-8222-222222222222")
QUARTER_ID = UUID("33333333-3333-4333-8333-333333333333")


class Database:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def session(self):
        async with self._sessions() as session:
            yield session


class Cache:
    async def get(self, _key: str) -> bytes | None:
        return None

    async def set(self, _key: str, _value: bytes, *, ttl_seconds: int) -> bool:
        assert ttl_seconds > 0
        return True


class Generations:
    async def current(self, _session: AsyncSession, _resource: str) -> int:
        return 1


class PublicQueries:
    limits = PublicQueryLimits(max_response_items=100)

    async def guard(self, _request, _session: AsyncSession, resource: str) -> None:
        assert resource in {"area-statistics", "area-statistic-series"}

    def is_timeout(self, _error: BaseException) -> bool:
        return False


@pytest_asyncio.fixture
async def statistics_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = get_settings().database_url
    schema = "test_statistics_query_contract"
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
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
CREATE TABLE analysis_areas (
  id integer PRIMARY KEY, uuid uuid NOT NULL UNIQUE, slug text NOT NULL UNIQUE,
  name text NOT NULL, area_type text NOT NULL, parent_id integer,
  geometry geometry(MultiPolygon,4326) NOT NULL,
  centroid geometry(Point,4326) NOT NULL, area_m2 double precision NOT NULL,
  source text NOT NULL, source_osm_type text, source_osm_id bigint,
  source_admin_level integer, source_place text, source_updated_at timestamptz,
  wikidata_id text, wikipedia_title text, wikidata_match_status text,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
)
""")
            )
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
            await connection.execute(
                text("""
INSERT INTO analysis_areas (
  id,uuid,slug,name,area_type,parent_id,geometry,centroid,area_m2,source,created_at,updated_at
) VALUES
  (1,:municipality,'flensburg','Flensburg','MUNICIPALITY',NULL,
   ST_GeomFromText('MULTIPOLYGON(((9.3 54.7,9.6 54.7,9.6 54.9,9.3 54.9,9.3 54.7)))',4326),
   ST_SetSRID(ST_Point(9.45,54.8),4326),50000000,'MANUAL',:now,:now),
  (2,:district,'nord','Nord','DISTRICT',1,
   ST_GeomFromText('MULTIPOLYGON(((9.4 54.75,9.5 54.75,9.5 54.85,9.4 54.85,9.4 54.75)))',4326),
   ST_SetSRID(ST_Point(9.45,54.8),4326),10000000,'MANUAL',:now,:now)
"""),
                {
                    "municipality": MUNICIPALITY_ID,
                    "district": DISTRICT_ID,
                    "now": datetime.now(UTC),
                },
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def area(identifier: UUID, slug: str, name: str, area_type: str) -> StatisticsArea:
    return StatisticsArea(id=identifier, slug=slug, name=name, area_type=area_type)


@pytest.mark.asyncio
async def test_real_statistics_queries_cover_selection_comparison_and_missing_cases(
    statistics_sessions: async_sessionmaker[AsyncSession],
) -> None:
    municipality = area(MUNICIPALITY_ID, "flensburg", "Flensburg", "MUNICIPALITY")
    district = area(DISTRICT_ID, "nord", "Nord", "DISTRICT")
    quarter = area(QUARTER_ID, "hafen", "Hafen", "QUARTER")
    service = SqlStatisticsQueryService()

    async with statistics_sessions() as session:
        municipality_result = await service.for_selection(
            session,
            StatisticsSelection(municipality, municipality, municipality, False),
        )
        assert municipality_result is not None
        assert municipality_result.latest[0].value == Decimal(110)
        assert municipality_result.latest[0].difference == Decimal(0)

        district_selection = StatisticsSelection(
            district, district, municipality, False
        )
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

        series = await service.series_for_selection(
            session, district_selection, "population"
        )
        assert series is not None
        assert [(point.period_start, point.value) for point in series.series] == [
            (date(2024, 1, 1), Decimal(90)),
            (date(2025, 1, 1), Decimal(95)),
        ]
        assert (
            await service.series_for_selection(session, district_selection, "missing")
            is None
        )
        unmapped = area(
            UUID("44444444-4444-4444-8444-444444444444"),
            "unknown",
            "Unknown",
            "DISTRICT",
        )
        assert (
            await service.for_selection(
                session,
                StatisticsSelection(unmapped, unmapped, municipality, False),
            )
            is None
        )

        assert (
            await session.scalar(text("SELECT count(*) FROM statistical_observations"))
            == 4
        )
        assert not session.in_transaction() or not session.dirty


@pytest.mark.asyncio
async def test_external_statistics_sdk_uuid_results_survive_the_http_boundary(
    statistics_sessions: async_sessionmaker[AsyncSession],
) -> None:
    app = FastAPI()
    app.include_router(
        create_router(
            Database(statistics_sessions),
            Cache(),
            Generations(),
            PublicQueries(),
            object(),
            object(),
            object(),
            object(),
            SqlStatisticsQueryService(),
            AnalysisAreasSettings(),
        ),
        prefix="/api/v1",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        summary = await client.get("/api/v1/analysis-areas/by-slug/nord/statistics")
        series = await client.get(
            "/api/v1/analysis-areas/by-slug/nord/statistics/population"
        )

    assert summary.status_code == 200, summary.text
    assert series.status_code == 200, series.text
    summary_body = summary.json()
    series_body = series.json()
    assert summary_body["area"]["id"] == str(DISTRICT_ID)
    assert summary_body["statistics_area"]["id"] == str(DISTRICT_ID)
    assert summary_body["latest"][0]["key"] == "population"
    assert series_body["area"]["id"] == str(DISTRICT_ID)
    assert series_body["statistics_area"]["id"] == str(DISTRICT_ID)
    assert series_body["series"][0]["period_start"] == "2024-01-01"
