"""Real PostGIS proof for the external module's SDK 1.13 reconcile path."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.integrations.module_host_ports import (
    HostCacheGenerations,
    HostOsmSnapshotQueries,
    HostPolygonIdentities,
    HostPolygonSpatialMatches,
)
from ocp_module_analysis_areas.application import (
    OsmAnalysisAreaSync,
    PolygonAnalysisAreaReconciler,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def sync_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = get_settings().database_url
    schema = "test_analysis_areas_sdk_113"
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
            await connection.execute(text("""
CREATE TABLE osm_features (
  osm_type text NOT NULL, osm_id bigint NOT NULL,
  geometry geometry(Geometry,4326) NOT NULL, tags jsonb NOT NULL,
  imported_at timestamptz NOT NULL, PRIMARY KEY (osm_type,osm_id)
)
"""))
            await connection.execute(text("""
CREATE TABLE cache_versions (
  namespace text PRIMARY KEY, version integer NOT NULL, updated_at timestamptz NOT NULL
)
"""))
            await connection.execute(text("""
CREATE TABLE analysis_areas (
  id serial PRIMARY KEY, uuid uuid NOT NULL UNIQUE, slug text NOT NULL UNIQUE,
  name text NOT NULL, area_type text NOT NULL, parent_id integer,
  geometry geometry(MultiPolygon,4326) NOT NULL,
  centroid geometry(Point,4326) NOT NULL, area_m2 double precision NOT NULL,
  source text NOT NULL, source_osm_type text, source_osm_id bigint,
  source_admin_level integer, source_place text, source_osm_wikidata text,
  source_osm_wikipedia text, source_updated_at timestamptz,
  wikidata_id text, wikidata_match_source text, wikidata_match_status text,
  wikidata_last_checked_at timestamptz, created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  UNIQUE (source,source_osm_type,source_osm_id)
)
"""))
            await connection.execute(text("""
CREATE TABLE user_polygons (
  id serial PRIMARY KEY, uuid uuid NOT NULL UNIQUE,
  geometry geometry(Geometry,4326) NOT NULL
)
"""))
            await connection.execute(text("""
CREATE TABLE polygon_analysis_areas (
  id serial PRIMARY KEY, polygon_id integer NOT NULL REFERENCES user_polygons(id),
  analysis_area_id integer NOT NULL REFERENCES analysis_areas(id),
  assignment_type text NOT NULL, overlap_ratio double precision,
  created_at timestamptz NOT NULL,
  UNIQUE (polygon_id,analysis_area_id)
)
"""))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


class Database:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def session(self):
        async with self._sessions() as session:
            yield session


class Logger:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def warning(self, *_args, **_kwargs) -> None:
        pass


@pytest.mark.asyncio
async def test_real_host_snapshot_and_generation_ports_sync_existing_identity(
    sync_sessions,
) -> None:
    imported_at = datetime(2026, 9, 1, tzinfo=UTC)
    async with sync_sessions() as session:
        await session.execute(text("""
INSERT INTO osm_features VALUES
 ('relation',1,ST_GeomFromText('POLYGON((9 54,10 54,10 55,9 55,9 54))',4326),
  '{"boundary":"administrative","name":"Flensburg","admin_level":"6"}',:at),
 ('relation',2,ST_GeomFromText('POLYGON((9.1 54.1,9.8 54.1,9.8 54.8,9.1 54.8,9.1 54.1))',4326),
  '{"boundary":"administrative","name":"Nord","admin_level":"9","wikidata":"Q2"}',:at),
 ('relation',3,ST_GeomFromText('POLYGON((9.2 54.2,9.5 54.2,9.5 54.5,9.2 54.5,9.2 54.2))',4326),
  '{"boundary":"administrative","name":"Hafen","admin_level":"10"}',:at)
"""), {"at": imported_at})
        await session.execute(text("""
INSERT INTO user_polygons (uuid,geometry) VALUES
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  ST_GeomFromText('POLYGON((8.6 53.6,10.1 53.6,10.1 55.1,8.6 55.1,8.6 53.6))',4326))
"""))
        await session.commit()

    service = OsmAnalysisAreaSync(
        Database(sync_sessions),
        HostOsmSnapshotQueries(),
        HostCacheGenerations(),
        PolygonAnalysisAreaReconciler(
            HostPolygonSpatialMatches(), HostPolygonIdentities()
        ),
        municipality_name="Flensburg",
        logger=Logger(),
    )
    first = await service.sync()
    async with sync_sessions() as session:
        before = (
            await session.execute(
                text("SELECT source_osm_id,uuid,slug,name FROM analysis_areas ORDER BY source_osm_id")
            )
        ).all()
        generations = dict((await session.execute(
            text("SELECT namespace,version FROM cache_versions ORDER BY namespace")
        )).all())
        relations = (
            await session.execute(text("""
SELECT polygon_id, analysis_area_id, assignment_type, overlap_ratio
FROM polygon_analysis_areas ORDER BY analysis_area_id
"""))
        ).all()
    second = await service.sync()
    async with sync_sessions() as session:
        after = (
            await session.execute(
                text("SELECT source_osm_id,uuid,slug,name FROM analysis_areas ORDER BY source_osm_id")
            )
        ).all()
        generations_after = dict((await session.execute(
            text("SELECT namespace,version FROM cache_versions ORDER BY namespace")
        )).all())

    assert first.created == 3
    assert first.counts == {"MUNICIPALITY": 1, "DISTRICT": 1, "QUARTER": 1}
    assert second.unchanged == 3
    assert before == after
    assert generations == generations_after == {"analysis-areas": 2, "analytics": 2}
    assert len(relations) == 3
    assert all(row.assignment_type == "POINT_ON_SURFACE" for row in relations)
    assert first.polygon_relations is not None
    assert first.polygon_relations.created == 3
    assert second.polygon_relations is not None
    assert second.polygon_relations.unchanged == 3
    assert not second.polygon_relations.changed


@pytest.mark.asyncio
async def test_invalid_source_geometry_is_repaired_before_containment(
    sync_sessions,
) -> None:
    imported_at = datetime(2026, 9, 1, tzinfo=UTC)
    async with sync_sessions() as session:
        await session.execute(
            text("""
INSERT INTO osm_features VALUES
 ('relation',10,ST_GeomFromText(
   'POLYGON((9 54,10 55,9 55,10 54,9 54))',4326),
  '{"boundary":"administrative","name":"Flensburg","admin_level":"6"}',:at),
 ('relation',11,ST_GeomFromText(
   'POLYGON((9.2 54.08,9.4 54.08,9.4 54.18,9.2 54.18,9.2 54.08))',4326),
  '{"boundary":"administrative","name":"Nord","admin_level":"9"}',:at),
 ('relation',12,ST_GeomFromText(
   'POLYGON((9.25 54.1,9.35 54.1,9.35 54.15,9.25 54.15,9.25 54.1))',4326),
  '{"boundary":"administrative","name":"Hafen","admin_level":"10"}',:at)
"""),
            {"at": imported_at},
        )
        source_valid = await session.scalar(
            text("SELECT ST_IsValid(geometry) FROM osm_features WHERE osm_id=10")
        )
        await session.commit()

    service = OsmAnalysisAreaSync(
        Database(sync_sessions),
        HostOsmSnapshotQueries(),
        HostCacheGenerations(),
        PolygonAnalysisAreaReconciler(
            HostPolygonSpatialMatches(), HostPolygonIdentities()
        ),
        municipality_name="Flensburg",
        logger=Logger(),
    )
    result = await service.sync()

    async with sync_sessions() as session:
        normalized_valid = await session.scalar(
            text("""
SELECT ST_IsValid(geometry) FROM analysis_areas
WHERE source='OSM' AND source_osm_id=10
""")
        )
        areas = (
            await session.execute(
                text("SELECT source_osm_id,area_type FROM analysis_areas ORDER BY source_osm_id")
            )
        ).all()

    assert source_valid is False
    assert normalized_valid is True
    assert result.created == 3
    assert result.counts == {"MUNICIPALITY": 1, "DISTRICT": 1, "QUARTER": 1}
    assert areas == [(10, "MUNICIPALITY"), (11, "DISTRICT"), (12, "QUARTER")]
    assert result.warnings == ["Flensburg: invalid source geometry was repaired"]
