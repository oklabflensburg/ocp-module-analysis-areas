"""Module-owned reconciliation of polygon-to-analysis-area relations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.modules.sdk import (
    PolygonIdentityPort,
    PolygonIdentityRequest,
    PolygonSpatialArea,
    PolygonSpatialMatchPort,
    PolygonSpatialMatchRequest,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ANALYSIS_AREAS_SQL = text("""
SELECT id, uuid, area_type, ST_AsEWKB(geometry) AS geometry_wkb
FROM analysis_areas
ORDER BY id
""")

CURRENT_RELATIONS_SQL = text("""
SELECT id, polygon_id, analysis_area_id, assignment_type, overlap_ratio
FROM polygon_analysis_areas
ORDER BY polygon_id, analysis_area_id
""")

INSERT_RELATION_SQL = text("""
INSERT INTO polygon_analysis_areas
  (polygon_id, analysis_area_id, assignment_type, overlap_ratio, created_at)
VALUES
  (:polygon_id, :analysis_area_id, 'POINT_ON_SURFACE', :overlap_ratio, now())
""")

UPDATE_RELATION_SQL = text("""
UPDATE polygon_analysis_areas
SET assignment_type='POINT_ON_SURFACE', overlap_ratio=:overlap_ratio
WHERE id=:id
""")

DELETE_RELATION_SQL = text("""
DELETE FROM polygon_analysis_areas WHERE id=:id
""")


@dataclass(frozen=True, slots=True)
class PolygonAnalysisAreaReconcileResult:
    matches: int = 0
    resolved_identities: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    missing_polygon_uuids: tuple[UUID, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.deleted)


@dataclass(frozen=True, slots=True)
class _Area:
    id: int
    external_id: str
    selection_group: str
    geometry_wkb: bytes


@dataclass(frozen=True, slots=True)
class _DesiredRelation:
    polygon_id: int
    analysis_area_id: int
    overlap_ratio: float | None


class PolygonAnalysisAreaReconciler:
    """Reconcile the complete relation snapshot without owning the transaction."""

    def __init__(
        self,
        spatial_matches: PolygonSpatialMatchPort,
        polygon_identities: PolygonIdentityPort,
    ) -> None:
        self._spatial_matches = spatial_matches
        self._polygon_identities = polygon_identities

    async def reconcile(
        self, session: AsyncSession
    ) -> PolygonAnalysisAreaReconcileResult:
        area_rows = (await session.execute(ANALYSIS_AREAS_SQL)).mappings().all()
        areas = tuple(
            _Area(
                id=int(row["id"]),
                external_id=str(row["uuid"]),
                selection_group=str(row["area_type"]),
                geometry_wkb=bytes(row["geometry_wkb"]),
            )
            for row in area_rows
        )
        areas_by_external_id = {area.external_id: area for area in areas}
        match_result = await self._spatial_matches.match_polygons(
            session,
            PolygonSpatialMatchRequest(
                tuple(
                    PolygonSpatialArea(
                        external_id=area.external_id,
                        selection_group=area.selection_group,
                        geometry_wkb=area.geometry_wkb,
                    )
                    for area in areas
                )
            ),
        )

        polygon_uuids = tuple(
            dict.fromkeys(UUID(match.polygon_id) for match in match_result.matches)
        )
        identity_result = await self._polygon_identities.resolve(
            session, PolygonIdentityRequest(polygon_uuids)
        )
        if identity_result.missing:
            return PolygonAnalysisAreaReconcileResult(
                matches=len(match_result.matches),
                resolved_identities=len(identity_result.resolved),
                missing_polygon_uuids=identity_result.missing,
            )

        identities = {identity.uuid: identity.id for identity in identity_result.resolved}
        desired: dict[tuple[int, int], _DesiredRelation] = {}
        for match in match_result.matches:
            area = areas_by_external_id.get(match.external_area_id)
            if area is None:
                raise RuntimeError(
                    "Polygon spatial match returned an unknown Analysis Area ID."
                )
            if match.selection_group != area.selection_group:
                raise RuntimeError(
                    "Polygon spatial match returned a mismatched selection group."
                )
            polygon_uuid = UUID(match.polygon_id)
            polygon_id = identities.get(polygon_uuid)
            if polygon_id is None:
                raise RuntimeError(
                    "Polygon identity result omitted a requested UUID without marking it missing."
                )
            relation = _DesiredRelation(
                polygon_id=polygon_id,
                analysis_area_id=area.id,
                overlap_ratio=(
                    float(match.overlap_ratio)
                    if match.overlap_ratio is not None
                    else None
                ),
            )
            key = (relation.polygon_id, relation.analysis_area_id)
            previous = desired.get(key)
            if previous is not None and previous != relation:
                raise RuntimeError("Polygon spatial match returned conflicting relations.")
            desired[key] = relation

        current_rows = (await session.execute(CURRENT_RELATIONS_SQL)).mappings().all()
        current = {
            (int(row["polygon_id"]), int(row["analysis_area_id"])): row
            for row in current_rows
        }
        created = updated = deleted = unchanged = 0

        for key, relation in desired.items():
            row = current.get(key)
            if row is None:
                await session.execute(
                    INSERT_RELATION_SQL,
                    {
                        "polygon_id": relation.polygon_id,
                        "analysis_area_id": relation.analysis_area_id,
                        "overlap_ratio": relation.overlap_ratio,
                    },
                )
                created += 1
            elif (
                row["assignment_type"] != "POINT_ON_SURFACE"
                or row["overlap_ratio"] != relation.overlap_ratio
            ):
                await session.execute(
                    UPDATE_RELATION_SQL,
                    {"id": int(row["id"]), "overlap_ratio": relation.overlap_ratio},
                )
                updated += 1
            else:
                unchanged += 1

        for key, row in current.items():
            if key not in desired:
                await session.execute(DELETE_RELATION_SQL, {"id": int(row["id"])})
                deleted += 1

        return PolygonAnalysisAreaReconcileResult(
            matches=len(match_result.matches),
            resolved_identities=len(identity_result.resolved),
            created=created,
            updated=updated,
            deleted=deleted,
            unchanged=unchanged,
        )
