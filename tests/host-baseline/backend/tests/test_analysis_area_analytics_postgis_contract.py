"""Real PostGIS regression coverage for the external Analytics HTTP path."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.integrations.module_host_ports import HostOsmSnapshotQueries
from app.platform.modules.sdk import (
    CountValue,
    OsmSnapshotQuery,
    PolygonMetrics,
    PublicQueryLimits,
)
from fastapi import FastAPI
from ocp_module_analysis_areas.api.router import create_router
from ocp_module_analysis_areas.settings import AnalysisAreasSettings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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
        assert resource == "area-analytics"

    def is_timeout(self, _error: BaseException) -> bool:
        return False


class PolygonAnalytics:
    async def metrics(self, _session, _scope, _filters) -> PolygonMetrics:
        return PolygonMetrics(
            polygon_count=1,
            occupied_count=1,
            vacant_count=0,
            chain_count=0,
            independent_count=1,
            known_occupancy_count=1,
            known_business_structure_count=1,
            total_area_m2=120,
            average_area_m2=120,
        )

    async def category_counts(self, _session, _scope, _filters) -> tuple[CountValue, ...]:
        return (CountValue(key="retail", count=1),)


class CapturingOsmSnapshots(HostOsmSnapshotQueries):
    query: OsmSnapshotQuery | None = None

    async def list_features(self, session, query):
        self.query = query
        return await super().list_features(session, query)


@pytest_asyncio.fixture
async def analytics_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], UUID, str]
]:
    url = get_settings().database_url
    schema = "test_analysis_areas_box3d"
    area_uuid = uuid4()
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except (ConnectionError, DBAPIError, OSError, OperationalError) as exc:
        await admin.dispose()
        pytest.skip(f"PostgreSQL/PostGIS is unavailable: {type(exc).__name__}")

    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    try:
        async with engine.begin() as connection:
            postgis_version = await connection.scalar(text("SELECT PostGIS_Lib_Version()"))
            await connection.execute(text("""
CREATE TABLE analysis_areas (
  id serial PRIMARY KEY, uuid uuid NOT NULL UNIQUE, slug text NOT NULL UNIQUE,
  name text NOT NULL, area_type text NOT NULL, parent_id integer,
  geometry geometry(MultiPolygon,4326) NOT NULL,
  centroid geometry(Point,4326) NOT NULL, area_m2 double precision NOT NULL,
  source text NOT NULL, source_osm_type text, source_osm_id bigint,
  source_admin_level integer, source_place text, source_osm_wikidata text,
  source_osm_wikipedia text, source_updated_at timestamptz,
  wikidata_id text, wikipedia_title text, wikidata_label text,
  wikidata_description text, wikidata_match_source text,
  wikidata_match_status text, wikidata_match_confidence double precision,
  wikidata_last_checked_at timestamptz, wikidata_verified boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
)
"""))
            await connection.execute(text("""
CREATE TABLE polygon_analysis_areas (
  id serial PRIMARY KEY, polygon_id integer NOT NULL,
  analysis_area_id integer NOT NULL REFERENCES analysis_areas(id),
  assignment_type text NOT NULL, overlap_ratio double precision,
  created_at timestamptz NOT NULL
)
"""))
            await connection.execute(text("""
CREATE TABLE osm_features (
  osm_type text NOT NULL, osm_id bigint NOT NULL,
  geometry geometry(Geometry,4326) NOT NULL, tags jsonb NOT NULL,
  imported_at timestamptz NOT NULL, PRIMARY KEY (osm_type,osm_id)
)
"""))
            await connection.execute(
                text("""
INSERT INTO analysis_areas (
  uuid,slug,name,area_type,geometry,centroid,area_m2,source,created_at,updated_at
) VALUES (
  :uuid,'box3d-regression','Box3D Regression','DISTRICT',
  ST_GeomFromText(
    'MULTIPOLYGON(((9.4 54.7,9.5 54.7,9.5 54.8,9.4 54.8,9.4 54.7)))',4326
  ),
  ST_SetSRID(ST_Point(9.45,54.75),4326),1000000,'MANUAL',:now,:now
)
"""),
                {"uuid": area_uuid, "now": datetime.now(UTC)},
            )
            await connection.execute(text("""
INSERT INTO osm_features VALUES
  ('node',1,ST_SetSRID(ST_Point(9.45,54.75),4326),'{"amenity":"cafe"}',now()),
  ('node',2,ST_SetSRID(ST_Point(10.0,55.0),4326),'{"shop":"outside"}',now())
"""))
        yield async_sessionmaker(engine, expire_on_commit=False), area_uuid, str(postgis_version)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_analytics_endpoint_executes_box3d_against_real_postgis(
    analytics_database: tuple[async_sessionmaker[AsyncSession], UUID, str],
) -> None:
    sessions, area_uuid, postgis_version = analytics_database
    osm_snapshots = CapturingOsmSnapshots()
    app = FastAPI()
    app.include_router(
        create_router(
            Database(sessions),
            Cache(),
            Generations(),
            PublicQueries(),
            object(),
            object(),
            PolygonAnalytics(),
            osm_snapshots,
            object(),
            AnalysisAreasSettings(),
        ),
        prefix="/api/v1",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/analysis-areas/{area_uuid}/analytics")

    assert postgis_version.startswith("3.")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area"]["slug"] == "box3d-regression"
    assert body["metrics"]["polygon_count"] == 1
    assert body["industry_distribution"] == [{"category": "retail", "count": 1}]
    assert body["poi_count"] == 1
    assert body["poi_categories"] == [{"category": "cafe", "count": 1}]
    assert body["retail_area_density_m2_per_km2"] == pytest.approx(120)
    assert osm_snapshots.query is not None
    assert osm_snapshots.query.bbox == pytest.approx((9.4, 54.7, 9.5, 54.8))
