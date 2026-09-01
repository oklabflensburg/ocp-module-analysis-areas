"""Module-owned OSM Analysis Areas synchronization over public SDK contracts."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.platform.modules.sdk import (
    CacheGenerationPort,
    DatabaseSessionProvider,
    OsmFeatureSnapshot,
    OsmSnapshotQuery,
    OsmSnapshotQueryPort,
    OsmTagFilter,
)
from sqlalchemy import text

from .polygon_reconcile import (
    PolygonAnalysisAreaReconciler,
    PolygonAnalysisAreaReconcileResult,
)

PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class PreparedFeature:
    osm_type: str
    osm_id: int
    tags: Mapping[str, str]
    imported_at: object
    source_geometry_wkb: bytes
    geometry_wkb: bytes
    centroid_wkb: bytes
    area_m2: float
    source_valid: bool
    valid: bool

    @property
    def admin_level(self) -> int | None:
        value = self.tags.get("admin_level", "")
        return int(value) if re.fullmatch(r"[0-9]+", value) else None


@dataclass(slots=True)
class AnalysisAreaSyncResult:
    municipality: str
    municipality_admin_level: int | None = None
    district_admin_level: int | None = None
    quarter_admin_level: int | None = None
    pages: int = 0
    features: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    polygon_relations: PolygonAnalysisAreaReconcileResult | None = None


NORMALIZE_SQL = text("""
WITH source AS (
  SELECT ST_GeomFromEWKB(:geometry) AS geometry
), normalized AS (
  SELECT geometry AS source_geometry,
    ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry), 3)) AS geometry
  FROM source
)
SELECT ST_AsEWKB(geometry) AS geometry,
  ST_AsEWKB(ST_PointOnSurface(geometry)) AS centroid,
  ST_Area(ST_Transform(geometry, 25832)) AS area_m2,
  ST_IsValid(source_geometry) AS source_valid,
  ST_IsValid(geometry) AS valid
FROM normalized
WHERE NOT ST_IsEmpty(geometry)
""")

COVERS_SQL = text("""
SELECT ST_Covers(
  ST_GeomFromEWKB(:container),
  ST_PointOnSurface(ST_GeomFromEWKB(:candidate))
)
""")

CURRENT_SQL = text("""
SELECT id FROM analysis_areas
WHERE source='OSM' AND source_osm_type=:osm_type AND source_osm_id=:osm_id
""")

UPSERT_SQL = text("""
INSERT INTO analysis_areas
  (uuid, slug, name, area_type, geometry, centroid, area_m2, source, source_osm_type,
   source_osm_id, source_admin_level, source_place, source_osm_wikidata,
   source_osm_wikipedia, source_updated_at, created_at, updated_at)
VALUES
  (:uuid, :slug, :name, :area_type, ST_GeomFromEWKB(:geometry),
   ST_GeomFromEWKB(:centroid), :area_m2, 'OSM', :osm_type, :osm_id, :admin_level,
   :place, :osm_wikidata, :osm_wikipedia, :source_updated_at, now(), now())
ON CONFLICT (source, source_osm_type, source_osm_id) DO UPDATE SET
  name=excluded.name, area_type=excluded.area_type, geometry=excluded.geometry,
  centroid=excluded.centroid, area_m2=excluded.area_m2,
  source_admin_level=excluded.source_admin_level, source_place=excluded.source_place,
  source_osm_wikidata=excluded.source_osm_wikidata,
  source_osm_wikipedia=excluded.source_osm_wikipedia,
  wikidata_match_status=CASE
    WHEN analysis_areas.wikidata_match_source='MANUAL'
      AND excluded.source_osm_wikidata IS NOT NULL
      AND excluded.source_osm_wikidata IS DISTINCT FROM analysis_areas.wikidata_id
      THEN 'CONFLICT'
    ELSE analysis_areas.wikidata_match_status END,
  wikidata_last_checked_at=CASE
    WHEN analysis_areas.wikidata_match_source='MANUAL'
      THEN analysis_areas.wikidata_last_checked_at
    WHEN excluded.source_osm_wikidata IS DISTINCT FROM analysis_areas.source_osm_wikidata
      OR excluded.source_osm_wikipedia IS DISTINCT FROM analysis_areas.source_osm_wikipedia
      THEN NULL
    ELSE analysis_areas.wikidata_last_checked_at END,
  source_updated_at=excluded.source_updated_at, updated_at=now()
WHERE analysis_areas.name IS DISTINCT FROM excluded.name
   OR analysis_areas.area_type IS DISTINCT FROM excluded.area_type
   OR analysis_areas.geometry IS DISTINCT FROM excluded.geometry
   OR analysis_areas.centroid IS DISTINCT FROM excluded.centroid
   OR analysis_areas.area_m2 IS DISTINCT FROM excluded.area_m2
   OR analysis_areas.source_admin_level IS DISTINCT FROM excluded.source_admin_level
   OR analysis_areas.source_place IS DISTINCT FROM excluded.source_place
   OR analysis_areas.source_osm_wikidata IS DISTINCT FROM excluded.source_osm_wikidata
   OR analysis_areas.source_osm_wikipedia IS DISTINCT FROM excluded.source_osm_wikipedia
   OR analysis_areas.source_updated_at IS DISTINCT FROM excluded.source_updated_at
RETURNING id
""")

PARENT_SQL = text("""
WITH desired AS (
  SELECT child.id,
    (SELECT candidate.id FROM analysis_areas candidate
     WHERE candidate.id<>child.id
       AND candidate.area_type=CASE child.area_type
         WHEN 'DISTRICT' THEN 'MUNICIPALITY' WHEN 'QUARTER' THEN 'DISTRICT' END
       AND ST_Covers(candidate.geometry, child.centroid)
     ORDER BY ST_Area(ST_Transform(
       ST_Intersection(candidate.geometry, child.geometry), 25832)) DESC,
       candidate.area_m2 ASC
     LIMIT 1) AS parent_id
  FROM analysis_areas child
  WHERE child.source='OSM' AND child.area_type IN ('DISTRICT','QUARTER')
)
UPDATE analysis_areas child SET parent_id=desired.parent_id, updated_at=now()
FROM desired
WHERE child.id=desired.id AND child.parent_id IS DISTINCT FROM desired.parent_id
""")


class OsmAnalysisAreaSync:
    def __init__(
        self,
        database: DatabaseSessionProvider,
        snapshots: OsmSnapshotQueryPort,
        generations: CacheGenerationPort,
        polygon_relations: PolygonAnalysisAreaReconciler,
        *,
        municipality_name: str,
        logger: Any,
    ) -> None:
        self._database = database
        self._snapshots = snapshots
        self._generations = generations
        self._polygon_relations = polygon_relations
        self._municipality_name = municipality_name
        self._logger = logger

    async def sync(self) -> AnalysisAreaSyncResult:
        report = AnalysisAreaSyncResult(municipality=self._municipality_name)
        self._logger.info("Analysis Areas OSM sync started")
        async with self._database.session() as session:
            administrative = await self._load(
                session,
                OsmSnapshotQuery(
                    geometry_kinds=("area",),
                    required_tag_keys=("admin_level",),
                    tag_filters=(OsmTagFilter("boundary", ("administrative",)),),
                    limit=PAGE_SIZE,
                ),
                report,
            )
            places = await self._load(
                session,
                OsmSnapshotQuery(
                    geometry_kinds=("area",),
                    tag_filters=(
                        OsmTagFilter(
                            "place", ("borough", "suburb", "quarter", "neighbourhood")
                        ),
                    ),
                    limit=PAGE_SIZE,
                ),
                report,
            )
            prepared_admin = await self._prepare(session, administrative)
            municipality = self._municipality(prepared_admin)
            report.municipality_admin_level = municipality.admin_level
            contained_admin = [
                feature
                for feature in prepared_admin
                if feature.admin_level is not None
                and feature.admin_level > municipality.admin_level
                and await self._covers(session, municipality, feature)
            ]
            levels = sorted({feature.admin_level for feature in contained_admin})
            report.district_admin_level = levels[0] if levels else None
            report.quarter_admin_level = levels[1] if len(levels) > 1 else None
            if report.district_admin_level is None:
                raise LookupError("No subordinate administrative area level was found")
            if report.quarter_admin_level is None:
                report.warnings.append(
                    "No second subordinate administrative level; polygonal places were checked"
                )

            selected: dict[tuple[str, int], tuple[PreparedFeature, str]] = {
                (municipality.osm_type, municipality.osm_id): (municipality, "MUNICIPALITY")
            }
            for feature in contained_admin:
                area_type = None
                if feature.admin_level == report.district_admin_level:
                    area_type = "DISTRICT"
                elif feature.admin_level == report.quarter_admin_level:
                    area_type = "QUARTER"
                if area_type:
                    selected[(feature.osm_type, feature.osm_id)] = (feature, area_type)
            for feature in await self._prepare(session, places):
                key = (feature.osm_type, feature.osm_id)
                if key not in selected and await self._covers(session, municipality, feature):
                    selected[key] = (
                        feature,
                        "DISTRICT"
                        if feature.tags.get("place") in {"borough", "suburb"}
                        else "QUARTER",
                    )

            report.counts = {"MUNICIPALITY": 0, "DISTRICT": 0, "QUARTER": 0}
            for feature, area_type in sorted(
                selected.values(), key=lambda item: ({"MUNICIPALITY": 1, "DISTRICT": 2, "QUARTER": 3}[item[1]], item[0].tags.get("name", ""))
            ):
                await self._upsert(session, feature, area_type, report)
                report.counts[area_type] += 1
            parent_result = await session.execute(PARENT_SQL)
            parent_changes = max(int(parent_result.rowcount or 0), 0)
            report.polygon_relations = await self._polygon_relations.reconcile(session)
            if report.polygon_relations.missing_polygon_uuids:
                self._logger.warning(
                    "Analysis Areas polygon relation reconcile skipped stale cleanup",
                    extra={
                        "polygon_matches": report.polygon_relations.matches,
                        "polygon_identities_resolved": report.polygon_relations.resolved_identities,
                        "polygon_identities_missing": len(
                            report.polygon_relations.missing_polygon_uuids
                        ),
                    },
                )
            if (
                report.created
                or report.updated
                or parent_changes
                or report.polygon_relations.changed
            ):
                await self._generations.bump(session, ("analysis-areas", "analytics"))
            await session.commit()

        self._logger.info(
            "Analysis Areas OSM sync completed",
            extra={
                "pages": report.pages,
                "features": report.features,
                "areas_created": report.created,
                "areas_updated": report.updated,
                "areas_unchanged": report.unchanged,
                "areas_removed": report.removed,
                "polygon_matches": report.polygon_relations.matches,
                "polygon_identities_resolved": report.polygon_relations.resolved_identities,
                "polygon_identities_missing": len(
                    report.polygon_relations.missing_polygon_uuids
                ),
                "relations_created": report.polygon_relations.created,
                "relations_updated": report.polygon_relations.updated,
                "relations_deleted": report.polygon_relations.deleted,
                "relations_unchanged": report.polygon_relations.unchanged,
            },
        )
        return report

    async def _load(self, session: Any, query: OsmSnapshotQuery, report: AnalysisAreaSyncResult) -> tuple[OsmFeatureSnapshot, ...]:
        items: list[OsmFeatureSnapshot] = []
        cursor = query.cursor
        while True:
            page = await self._snapshots.list_features(
                session,
                OsmSnapshotQuery(
                    osm_types=query.osm_types,
                    geometry_kinds=query.geometry_kinds,
                    required_tag_keys=query.required_tag_keys,
                    tag_filters=query.tag_filters,
                    bbox=query.bbox,
                    cursor=cursor,
                    limit=query.limit,
                ),
            )
            report.pages += 1
            report.features += len(page.items)
            items.extend(page.items)
            if page.next_cursor is None:
                return tuple(items)
            if page.next_cursor == cursor:
                raise RuntimeError("OSM snapshot pagination returned a non-advancing cursor")
            cursor = page.next_cursor

    async def _prepare(self, session: Any, features: Sequence[OsmFeatureSnapshot]) -> list[PreparedFeature]:
        prepared: list[PreparedFeature] = []
        for feature in features:
            row = (
                await session.execute(NORMALIZE_SQL, {"geometry": feature.geometry_wkb})
            ).mappings().first()
            if row is None:
                continue
            prepared.append(
                PreparedFeature(
                    osm_type=feature.osm_type,
                    osm_id=feature.osm_id,
                    tags=feature.tags,
                    imported_at=feature.imported_at,
                    source_geometry_wkb=feature.geometry_wkb,
                    geometry_wkb=bytes(row["geometry"]),
                    centroid_wkb=bytes(row["centroid"]),
                    area_m2=float(row["area_m2"]),
                    source_valid=bool(row["source_valid"]),
                    valid=bool(row["valid"]),
                )
            )
        return prepared

    def _municipality(self, features: Sequence[PreparedFeature]) -> PreparedFeature:
        matches = [
            feature
            for feature in features
            if feature.admin_level is not None
            and feature.tags.get("name", "").casefold() == self._municipality_name.casefold()
        ]
        if not matches:
            raise LookupError(
                f"No administrative OSM area found for {self._municipality_name!r}"
            )
        return min(matches, key=lambda feature: (feature.admin_level, -feature.area_m2))

    async def _covers(self, session: Any, container: PreparedFeature, candidate: PreparedFeature) -> bool:
        return bool(
            await session.scalar(
                COVERS_SQL,
                {
                    "container": container.geometry_wkb,
                    "candidate": candidate.geometry_wkb,
                },
            )
        )

    async def _upsert(
        self,
        session: Any,
        feature: PreparedFeature,
        area_type: str,
        report: AnalysisAreaSyncResult,
    ) -> None:
        name = str(
            feature.tags.get("name")
            or feature.tags.get("name:de")
            or f"OSM {feature.osm_id}"
        ).strip()
        values = {
            "uuid": uuid.uuid4(),
            "slug": _slug(name, feature.osm_id),
            "name": name,
            "area_type": area_type,
            "geometry": feature.geometry_wkb,
            "centroid": feature.centroid_wkb,
            "area_m2": feature.area_m2,
            "osm_type": feature.osm_type,
            "osm_id": feature.osm_id,
            "admin_level": feature.admin_level,
            "place": feature.tags.get("place"),
            "osm_wikidata": feature.tags.get("wikidata"),
            "osm_wikipedia": feature.tags.get("wikipedia"),
            "source_updated_at": feature.imported_at,
        }
        existed = (await session.execute(CURRENT_SQL, values)).first() is not None
        changed = (await session.execute(UPSERT_SQL, values)).first() is not None
        if not changed:
            report.unchanged += 1
        elif existed:
            report.updated += 1
        else:
            report.created += 1
        if not feature.source_valid:
            report.warnings.append(f"{name}: invalid source geometry was repaired")
        if not feature.valid:
            report.warnings.append(f"{name}: geometry remains invalid after normalization")


def _slug(value: str, osm_id: int) -> str:
    normalized = (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "gebiet"
    return f"{normalized}-{osm_id}"
