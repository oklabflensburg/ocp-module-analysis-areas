"""Pure Wikidata matching values owned by Analysis Areas."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AreaSnapshot:
    id: int
    name: str
    area_type: str
    latitude: float
    longitude: float
    source_osm_wikidata: str | None = None
    source_osm_wikipedia: str | None = None
    parent_name: str | None = None
    parent_wikidata_id: str | None = None
    municipality_name: str | None = None


@dataclass(frozen=True, slots=True)
class WikidataEntity:
    id: str
    label: str | None
    description: str | None
    wikipedia_title: str | None
    aliases: tuple[str, ...] = ()
    latitude: float | None = None
    longitude: float | None = None
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Match:
    status: str
    source: str | None = None
    confidence: float | None = None
    entity: WikidataEntity | None = None
