from __future__ import annotations

from uuid import UUID

import pytest
from app.platform.modules.sdk import (
    PolygonIdentity,
    PolygonIdentityResult,
    PolygonSpatialMatch,
    PolygonSpatialMatchResult,
)

from ocp_module_analysis_areas.application.polygon_reconcile import (
    ANALYSIS_AREAS_SQL,
    CURRENT_RELATIONS_SQL,
    DELETE_RELATION_SQL,
    INSERT_RELATION_SQL,
    UPDATE_RELATION_SQL,
    PolygonAnalysisAreaReconciler,
)

POLYGON_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
POLYGON_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
AREA_X = UUID("11111111-1111-4111-8111-111111111111")
AREA_Y = UUID("22222222-2222-4222-8222-222222222222")


class Mappings:
    def __init__(self, values):
        self._values = values

    def mappings(self):
        return self

    def all(self):
        return list(self._values)


class Session:
    def __init__(self, areas, relations=()) -> None:
        self.areas = list(areas)
        self.relations = {row["id"]: dict(row) for row in relations}
        self.next_id = max(self.relations, default=0) + 1
        self.writes: list[object] = []

    async def execute(self, statement, parameters=None):
        parameters = parameters or {}
        if statement is ANALYSIS_AREAS_SQL:
            return Mappings(self.areas)
        if statement is CURRENT_RELATIONS_SQL:
            return Mappings(self.relations.values())
        self.writes.append(statement)
        if statement is INSERT_RELATION_SQL:
            self.relations[self.next_id] = {
                "id": self.next_id,
                "polygon_id": parameters["polygon_id"],
                "analysis_area_id": parameters["analysis_area_id"],
                "assignment_type": "POINT_ON_SURFACE",
                "overlap_ratio": parameters["overlap_ratio"],
            }
            self.next_id += 1
        elif statement is UPDATE_RELATION_SQL:
            self.relations[parameters["id"]].update(
                assignment_type="POINT_ON_SURFACE",
                overlap_ratio=parameters["overlap_ratio"],
            )
        elif statement is DELETE_RELATION_SQL:
            del self.relations[parameters["id"]]
        else:
            raise AssertionError(str(statement))
        return Mappings(())


class SpatialMatches:
    def __init__(self, matches) -> None:
        self.matches = tuple(matches)
        self.calls = []

    async def match_polygons(self, session, request):
        self.calls.append((session, request))
        return PolygonSpatialMatchResult(self.matches)


class Identities:
    def __init__(self, resolved=(), missing=()) -> None:
        self.result = PolygonIdentityResult(tuple(resolved), tuple(missing))
        self.calls = []

    async def resolve(self, session, request):
        self.calls.append((session, request))
        return self.result


def area(area_id: int, value: UUID, group: str) -> dict:
    return {
        "id": area_id,
        "uuid": value,
        "area_type": group,
        "geometry_wkb": f"geometry-{area_id}".encode(),
    }


def match(polygon: UUID, target: UUID, group: str, overlap: float) -> PolygonSpatialMatch:
    return PolygonSpatialMatch(str(polygon), str(target), group, overlap)


@pytest.mark.asyncio
async def test_create_update_delete_and_second_run_are_idempotent() -> None:
    session = Session(
        [area(10, AREA_X, "DISTRICT"), area(20, AREA_Y, "QUARTER")],
        [
            {
                "id": 1,
                "polygon_id": 7,
                "analysis_area_id": 10,
                "assignment_type": "POINT_ON_SURFACE",
                "overlap_ratio": 0.25,
            },
            {
                "id": 2,
                "polygon_id": 11,
                "analysis_area_id": 10,
                "assignment_type": "POINT_ON_SURFACE",
                "overlap_ratio": 0.9,
            },
        ],
    )
    spatial = SpatialMatches(
        [
            match(POLYGON_A, AREA_X, "DISTRICT", 0.5),
            match(POLYGON_A, AREA_Y, "QUARTER", 0.75),
        ]
    )
    identities = Identities([PolygonIdentity(7, POLYGON_A)])
    reconciler = PolygonAnalysisAreaReconciler(spatial, identities)

    first = await reconciler.reconcile(session)
    writes_after_first = len(session.writes)
    second = await reconciler.reconcile(session)

    assert (first.created, first.updated, first.deleted, first.unchanged) == (1, 1, 1, 0)
    assert (second.created, second.updated, second.deleted, second.unchanged) == (0, 0, 0, 2)
    assert len(session.writes) == writes_after_first
    assert len(identities.calls) == 2
    assert identities.calls[0][1].polygon_uuids == (POLYGON_A,)
    assert [item.external_id for item in spatial.calls[0][1].areas] == [str(AREA_X), str(AREA_Y)]
    assert [item.selection_group for item in spatial.calls[0][1].areas] == [
        "DISTRICT",
        "QUARTER",
    ]


@pytest.mark.asyncio
async def test_missing_identity_skips_all_relation_mutation_and_stale_cleanup() -> None:
    original = {
        "id": 1,
        "polygon_id": 7,
        "analysis_area_id": 10,
        "assignment_type": "POINT_ON_SURFACE",
        "overlap_ratio": 0.5,
    }
    session = Session([area(10, AREA_X, "DISTRICT")], [original])
    reconciler = PolygonAnalysisAreaReconciler(
        SpatialMatches([match(POLYGON_B, AREA_X, "DISTRICT", 0.75)]),
        Identities(missing=[POLYGON_B]),
    )

    result = await reconciler.reconcile(session)

    assert result.missing_polygon_uuids == (POLYGON_B,)
    assert not result.changed
    assert session.writes == []
    assert list(session.relations.values()) == [original]


@pytest.mark.asyncio
async def test_multiple_polygons_and_selection_groups_share_one_identity_batch() -> None:
    spatial = SpatialMatches(
        [
            match(POLYGON_A, AREA_X, "DISTRICT", 1.0),
            match(POLYGON_B, AREA_X, "DISTRICT", 0.8),
            match(POLYGON_A, AREA_Y, "QUARTER", 0.6),
        ]
    )
    identities = Identities(
        [PolygonIdentity(7, POLYGON_A), PolygonIdentity(11, POLYGON_B)]
    )
    session = Session(
        [area(10, AREA_X, "DISTRICT"), area(20, AREA_Y, "QUARTER")]
    )

    result = await PolygonAnalysisAreaReconciler(spatial, identities).reconcile(session)

    assert result.created == 3
    assert len(identities.calls) == 1
    assert identities.calls[0][1].polygon_uuids == (POLYGON_A, POLYGON_B)


@pytest.mark.asyncio
async def test_changed_match_replaces_stale_area_relation() -> None:
    session = Session(
        [area(10, AREA_X, "DISTRICT"), area(20, AREA_Y, "DISTRICT")],
        [
            {
                "id": 1,
                "polygon_id": 7,
                "analysis_area_id": 10,
                "assignment_type": "POINT_ON_SURFACE",
                "overlap_ratio": 0.9,
            }
        ],
    )
    reconciler = PolygonAnalysisAreaReconciler(
        SpatialMatches([match(POLYGON_A, AREA_Y, "DISTRICT", 0.8)]),
        Identities([PolygonIdentity(7, POLYGON_A)]),
    )

    result = await reconciler.reconcile(session)

    assert (result.created, result.deleted) == (1, 1)
    assert {
        (row["polygon_id"], row["analysis_area_id"])
        for row in session.relations.values()
    } == {(7, 20)}
