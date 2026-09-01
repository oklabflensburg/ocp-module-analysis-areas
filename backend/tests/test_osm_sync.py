from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from app.platform.modules.sdk import (
    OsmFeatureCursor,
    OsmFeatureSnapshot,
    OsmFeatureSnapshotPage,
)

from ocp_module_analysis_areas.application.osm_sync import (
    COVERS_SQL,
    CURRENT_SQL,
    NORMALIZE_SQL,
    PARENT_SQL,
    UPSERT_SQL,
    OsmAnalysisAreaSync,
    PreparedFeature,
)


class Rows:
    def __init__(self, values=(), *, rowcount=0) -> None:
        self.values = list(values)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self.values[0] if self.values else None


class State:
    def __init__(self) -> None:
        self.areas: dict[tuple[str, int], dict] = {}
        self.commits = 0


class Session:
    def __init__(self, state: State) -> None:
        self.state = state

    async def execute(self, statement, parameters=None):
        parameters = parameters or {}
        if statement is NORMALIZE_SQL:
            geometry = bytes(parameters["geometry"])
            return Rows(
                [
                    {
                        "geometry": geometry,
                        "centroid": b"centroid-" + geometry,
                        "area_m2": float(int.from_bytes(geometry[-1:], "big") + 1),
                        "source_valid": True,
                        "valid": True,
                    }
                ]
            )
        key = (parameters.get("osm_type"), parameters.get("osm_id"))
        if statement is CURRENT_SQL:
            return Rows([(self.state.areas[key]["uuid"],)] if key in self.state.areas else [])
        if statement is UPSERT_SQL:
            previous = self.state.areas.get(key)
            comparable = {
                name: value
                for name, value in parameters.items()
                if name not in {"uuid", "slug"}
            }
            if previous is not None and previous["comparable"] == comparable:
                return Rows([])
            self.state.areas[key] = {
                "uuid": previous["uuid"] if previous else parameters["uuid"],
                "slug": previous["slug"] if previous else parameters["slug"],
                "comparable": comparable,
            }
            return Rows([(len(self.state.areas),)])
        if statement is PARENT_SQL:
            return Rows(rowcount=0)
        raise AssertionError(str(statement))

    async def scalar(self, _statement, _parameters):
        return True

    async def commit(self):
        self.state.commits += 1


class Database:
    def __init__(self) -> None:
        self.state = State()

    @asynccontextmanager
    async def session(self):
        yield Session(self.state)


def feature(osm_id: int, tags: dict[str, str]) -> OsmFeatureSnapshot:
    return OsmFeatureSnapshot(
        "relation",
        osm_id,
        tags,
        bytes([osm_id]),
        (9.0, 54.0, 10.0, 55.0),
        datetime(2026, 9, 1, tzinfo=UTC),
    )


class Snapshots:
    def __init__(self) -> None:
        self.calls = []

    async def list_features(self, _session, query):
        self.calls.append(query)
        boundary = any(item.key == "boundary" for item in query.tag_filters)
        if boundary and query.cursor is None:
            return OsmFeatureSnapshotPage(
                (feature(1, {"name": "Flensburg", "admin_level": "6", "boundary": "administrative"}),),
                OsmFeatureCursor("relation", 1),
            )
        if boundary:
            return OsmFeatureSnapshotPage(
                (feature(2, {"name": "Nord", "admin_level": "9", "boundary": "administrative", "wikidata": "Q2"}),)
            )
        return OsmFeatureSnapshotPage(
            (feature(3, {"name": "Hafen", "place": "quarter", "wikipedia": "de:Hafen"}),)
        )


class Generations:
    def __init__(self) -> None:
        self.calls = []

    async def bump(self, session, resources):
        self.calls.append((session, tuple(resources)))


class Logger:
    def info(self, *_args, **_kwargs):
        pass


@pytest.mark.asyncio
async def test_osm_pagination_upsert_and_duplicate_delivery_are_idempotent() -> None:
    database = Database()
    snapshots = Snapshots()
    generations = Generations()
    service = OsmAnalysisAreaSync(
        database,
        snapshots,
        generations,
        municipality_name="Flensburg",
        logger=Logger(),
    )

    first = await service.sync()
    identities = {
        key: (value["uuid"], value["slug"]) for key, value in database.state.areas.items()
    }
    second = await service.sync()  # same at-least-once event delivered again

    assert first.pages == 3
    assert first.created == 3 and first.updated == first.unchanged == 0
    assert first.counts == {"MUNICIPALITY": 1, "DISTRICT": 1, "QUARTER": 1}
    assert second.created == second.updated == 0 and second.unchanged == 3
    assert identities == {
        key: (value["uuid"], value["slug"]) for key, value in database.state.areas.items()
    }
    assert len(generations.calls) == 1
    assert generations.calls[0][1] == ("analysis-areas", "analytics")
    assert all(query.limit == 500 for query in snapshots.calls)
    assert snapshots.calls[1].cursor == OsmFeatureCursor("relation", 1)


@pytest.mark.asyncio
async def test_containment_uses_normalized_geometry() -> None:
    class CoversSession:
        parameters = None

        async def scalar(self, statement, parameters):
            assert statement is COVERS_SQL
            self.parameters = parameters
            return True

    def prepared(osm_id: int, source: bytes, normalized: bytes) -> PreparedFeature:
        return PreparedFeature(
            osm_type="relation",
            osm_id=osm_id,
            tags={},
            imported_at=datetime(2026, 9, 1, tzinfo=UTC),
            source_geometry_wkb=source,
            geometry_wkb=normalized,
            centroid_wkb=b"centroid",
            area_m2=1.0,
            source_valid=False,
            valid=True,
        )

    session = CoversSession()
    service = OsmAnalysisAreaSync(
        Database(), Snapshots(), Generations(), municipality_name="Flensburg", logger=Logger()
    )

    assert await service._covers(
        session,
        prepared(1, b"raw-container", b"normalized-container"),
        prepared(2, b"raw-candidate", b"normalized-candidate"),
    )
    assert session.parameters == {
        "container": b"normalized-container",
        "candidate": b"normalized-candidate",
    }


def test_osm_sql_only_writes_module_owned_tables_and_preserves_manual_match() -> None:
    upsert = str(UPSERT_SQL)
    assert "ON CONFLICT (source, source_osm_type, source_osm_id)" in upsert
    assert "wikidata_match_source='MANUAL'" in upsert
    assert "uuid=excluded.uuid" not in upsert
    assert "slug=excluded.slug" not in upsert
    combined = "\n".join(map(str, (CURRENT_SQL, NORMALIZE_SQL, UPSERT_SQL, PARENT_SQL)))
    assert "osm_features" not in combined
    assert "user_polygons" not in combined
