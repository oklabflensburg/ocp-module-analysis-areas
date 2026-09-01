"""Wikidata enrichment workflow with short, separated DB phases."""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.platform.modules.sdk import CacheGenerationPort, CachePort, DatabaseSessionProvider
from sqlalchemy import text

from ..contracts import WikidataSyncResult
from ..domain.wikidata import (
    AreaSnapshot,
    Match,
    WikidataEntity,
)
from ..integrations.wikidata import QID_RE, WikidataClient, wikipedia_title

PUBLIC_STATUSES = {"VERIFIED", "AUTO_MATCHED"}
GEOGRAPHIC_DESCRIPTION_TERMS = (
    "stadt",
    "gemeinde",
    "stadtteil",
    "quartier",
    "ort",
    "gebiet",
    "district",
    "municipality",
    "borough",
    "neighborhood",
    "neighbourhood",
    "village",
)
NON_GEOGRAPHIC_DESCRIPTION_TERMS = (
    "person",
    "unternehmen",
    "company",
    "film",
    "album",
    "bahnhof",
    "station",
    "straße",
    "strasse",
    "road",
    "begriffsklärung",
    "disambiguation",
)

SNAPSHOT_SQL = text("""
SELECT area.id, area.name, area.area_type, area.source_osm_wikidata,
  area.source_osm_wikipedia, parent.name AS parent_name,
  parent.wikidata_id AS parent_wikidata_id,
  COALESCE(
    municipality.name,
    CASE WHEN area.area_type='MUNICIPALITY' THEN area.name END
  ) AS municipality_name,
  ST_Y(area.centroid) AS latitude, ST_X(area.centroid) AS longitude
FROM analysis_areas area
LEFT JOIN analysis_areas parent ON parent.id=area.parent_id
LEFT JOIN analysis_areas municipality ON municipality.id=CASE
  WHEN area.area_type='DISTRICT' THEN parent.id
  WHEN area.area_type='QUARTER' THEN parent.parent_id END
WHERE area.wikidata_match_source IS DISTINCT FROM 'MANUAL'
  AND (:force OR area.wikidata_last_checked_at IS NULL
    OR area.wikidata_last_checked_at < :stale_before
    OR area.wikidata_match_status NOT IN ('VERIFIED','AUTO_MATCHED'))
ORDER BY CASE area.area_type WHEN 'MUNICIPALITY' THEN 1 WHEN 'DISTRICT' THEN 2 ELSE 3 END,
  area.name
""")

PERSIST_SQL = text("""
UPDATE analysis_areas SET
  wikidata_id=:wikidata_id, wikipedia_title=:wikipedia_title,
  wikidata_label=:label, wikidata_description=:description,
  wikidata_match_source=:source, wikidata_match_status=:status,
  wikidata_match_confidence=:confidence, wikidata_last_checked_at=now(),
  wikidata_verified=false, updated_at=now()
WHERE id=:area_id AND wikidata_match_source IS DISTINCT FROM 'MANUAL'
RETURNING id
""")

MANUAL_SQL = text("""
UPDATE analysis_areas SET wikidata_id=:qid, wikipedia_title=:title,
  wikidata_label=:label, wikidata_description=:description,
  wikidata_match_source='MANUAL', wikidata_match_status='VERIFIED',
  wikidata_match_confidence=1, wikidata_verified=true,
  wikidata_last_checked_at=now(), updated_at=now()
WHERE id=:area_id
RETURNING id
""")


class AreaNotFoundError(LookupError):
    pass


class AmbiguousAreaError(ValueError):
    def __init__(self, slugs: tuple[str, ...]) -> None:
        self.slugs = slugs
        super().__init__("Area name is ambiguous: " + ", ".join(slugs))


class WikidataNameMismatchError(ValueError):
    pass


@dataclass(slots=True)
class _MutableReport:
    checked: int = 0
    osm_wikidata: int = 0
    osm_wikipedia: int = 0
    search: int = 0
    manual: int = 0
    not_found: int = 0
    ambiguous: int = 0
    invalid: int = 0
    conflicts: int = 0
    errors: list[str] = field(default_factory=list)


class WikidataEnrichmentService:
    def __init__(
        self,
        database: DatabaseSessionProvider,
        cache: CachePort,
        cache_generations: CacheGenerationPort,
        client: WikidataClient,
        *,
        stale_days: int,
    ) -> None:
        self._database = database
        self._cache = cache
        self._cache_generations = cache_generations
        self._client = client
        self._stale_days = stale_days

    async def resolve_area(self, area: AreaSnapshot) -> Match:
        osm_qid = (area.source_osm_wikidata or "").strip()
        title = wikipedia_title(area.source_osm_wikipedia)
        if osm_qid:
            if not QID_RE.fullmatch(osm_qid):
                return Match("INVALID", "OSM_WIKIDATA")
            entity = await self._client.entity(osm_qid)
            if entity is None:
                return Match("NOT_FOUND", "OSM_WIKIDATA")
            if title:
                wikipedia_entity = await self._client.entity_from_dewiki(title)
                if wikipedia_entity is not None and wikipedia_entity.id != entity.id:
                    return Match("CONFLICT", "OSM_WIKIDATA", 1.0, entity)
            return Match("AUTO_MATCHED", "OSM_WIKIDATA", 1.0, entity)
        if title:
            entity = await self._client.entity_from_dewiki(title)
            if entity is not None:
                return Match("AUTO_MATCHED", "OSM_WIKIPEDIA", 0.95, entity)
        context = " ".join(
            filter(
                None,
                (
                    area.name,
                    area.parent_name,
                    area.municipality_name,
                    "Deutschland",
                ),
            )
        )
        candidates = await self._client.search(context)
        if not candidates:
            candidates = await self._client.search(area.name)
        ranked = sorted(
            ((self.validate_candidate(area, candidate), candidate) for candidate in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        accepted = [(score, candidate) for score, candidate in ranked if score >= 0.85]
        if not accepted:
            return Match("NOT_FOUND")
        if len(accepted) > 1 and accepted[0][0] - accepted[1][0] < 0.1:
            return Match("AMBIGUOUS")
        score, candidate = accepted[0]
        return Match("AUTO_MATCHED", "WIKIDATA_SEARCH", score, candidate)

    @staticmethod
    def validate_candidate(area: AreaSnapshot, candidate: WikidataEntity) -> float:
        names = {candidate.label or "", *candidate.aliases}
        score = 0.35 if area.name.casefold() in {name.casefold() for name in names} else 0.0
        description = (candidate.description or "").casefold()
        if any(term in description for term in NON_GEOGRAPHIC_DESCRIPTION_TERMS):
            return 0.0
        if candidate.latitude is not None and candidate.longitude is not None:
            distance = _distance_km(
                area.latitude,
                area.longitude,
                candidate.latitude,
                candidate.longitude,
            )
            maximum = 10.0 if area.area_type == "MUNICIPALITY" else 3.0
            if distance <= maximum:
                score += 0.4
            elif distance > maximum * 4:
                return 0.0
        parent_name = (area.parent_name or area.municipality_name or "").casefold()
        if (
            (area.parent_wikidata_id and area.parent_wikidata_id in candidate.parent_ids)
            or (parent_name and parent_name in description)
            or (
                area.area_type == "MUNICIPALITY"
                and any(term in description for term in GEOGRAPHIC_DESCRIPTION_TERMS)
            )
        ):
            score += 0.25
        return round(score, 2)

    async def sync(self, *, force: bool = False) -> WikidataSyncResult:
        snapshots = await self._snapshots(force=force)
        report = _MutableReport()
        resolved: list[tuple[int, Match]] = []
        for area in snapshots:
            report.checked += 1
            try:
                match = await self.resolve_area(area)
            except Exception as exc:  # noqa: BLE001 - one unavailable entity must not abort bulk
                report.errors.append(f"{area.name}: {type(exc).__name__}")
                continue
            resolved.append((area.id, match))
            _count(report, match)

        mutated = False
        if resolved:
            async with self._database.session() as session:
                writes = 0
                for area_id, match in resolved:
                    writes += int(await _persist_match(session, area_id, match))
                if writes:
                    await self._cache_generations.bump(session, ("analysis-areas",))
                    await session.commit()
                    mutated = True
            if mutated:
                await self._cache.clear()
        return WikidataSyncResult(
            checked=report.checked,
            osm_wikidata=report.osm_wikidata,
            osm_wikipedia=report.osm_wikipedia,
            search=report.search,
            manual=report.manual,
            not_found=report.not_found,
            ambiguous=report.ambiguous,
            invalid=report.invalid,
            conflicts=report.conflicts,
            errors=tuple(report.errors),
        )

    async def set_manual_match(
        self,
        reference: str,
        qid: str,
        *,
        allow_name_mismatch: bool = False,
    ) -> None:
        if not QID_RE.fullmatch(qid):
            raise ValueError("Wikidata ID must use the form Q123")
        area_id, area_name = await self._resolve_reference(reference)
        entity = await self._client.entity(qid)
        if entity is None:
            raise LookupError(f"Wikidata entity does not exist: {qid}")
        candidate_names = {
            value.casefold() for value in (entity.label, *entity.aliases) if value
        }
        if area_name.casefold() not in candidate_names and not allow_name_mismatch:
            raise WikidataNameMismatchError(
                f"Area {area_name!r} does not match Wikidata label {entity.label!r}"
            )
        async with self._database.session() as session:
            result = await session.execute(
                MANUAL_SQL,
                {
                    "area_id": area_id,
                    "qid": qid,
                    "title": entity.wikipedia_title,
                    "label": entity.label,
                    "description": entity.description,
                },
            )
            if result.first() is None:
                raise AreaNotFoundError(reference)
            await self._cache_generations.bump(session, ("analysis-areas",))
            await session.commit()
        await self._cache.clear()

    async def _snapshots(self, *, force: bool) -> tuple[AreaSnapshot, ...]:
        stale_before = datetime.now(UTC) - timedelta(days=self._stale_days)
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    SNAPSHOT_SQL,
                    {"force": force, "stale_before": stale_before},
                )
            ).mappings().all()
            return tuple(AreaSnapshot(**dict(row)) for row in rows)

    async def _resolve_reference(self, reference: str) -> tuple[int, str]:
        async with self._database.session() as session:
            exact = (
                await session.execute(
                    text("SELECT id,name FROM analysis_areas WHERE slug=:reference"),
                    {"reference": reference},
                )
            ).first()
            if exact is not None:
                return int(exact[0]), str(exact[1])
            rows = (
                await session.execute(
                    text(
                        "SELECT id,name,slug FROM analysis_areas "
                        "WHERE lower(name)=:name ORDER BY slug"
                    ),
                    {"name": reference.casefold()},
                )
            ).all()
        if not rows:
            raise AreaNotFoundError(reference)
        if len(rows) > 1:
            raise AmbiguousAreaError(tuple(str(row[2]) for row in rows))
        return int(rows[0][0]), str(rows[0][1])


async def _persist_match(session, area_id: int, match: Match) -> bool:
    entity = match.entity
    result = await session.execute(
        PERSIST_SQL,
        {
            "area_id": area_id,
            "wikidata_id": entity.id if entity else None,
            "wikipedia_title": entity.wikipedia_title if entity else None,
            "label": entity.label if entity else None,
            "description": entity.description if entity else None,
            "source": match.source,
            "status": match.status,
            "confidence": match.confidence,
        },
    )
    return result.first() is not None


def _count(report: _MutableReport, match: Match) -> None:
    if match.status == "INVALID":
        report.invalid += 1
    elif match.status == "CONFLICT":
        report.conflicts += 1
    elif match.status == "AMBIGUOUS":
        report.ambiguous += 1
    elif match.status == "NOT_FOUND":
        report.not_found += 1
    elif match.source == "OSM_WIKIDATA":
        report.osm_wikidata += 1
    elif match.source == "OSM_WIKIPEDIA":
        report.osm_wikipedia += 1
    elif match.source == "WIKIDATA_SEARCH":
        report.search += 1
    else:
        report.not_found += 1


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
