# OSM/Wikidata parity matrix

Historical implementation reference: `open-city-planner@4468b0414cff4370b96023eb2ff578b2f07f71fd^`.
Current production contract: `open-city-planner@3bf1d00c687dd5ff9a5e912fd947d2d2d16dc667`,
Backend Module SDK `1.13.0`.

| Historical function | New owner / implementation | Public Host dependency | Tests | Status |
| --- | --- | --- | --- | --- |
| Municipality lookup, administrative-level inference and polygonal-place selection | module `application/osm_sync.py` | `platform.osm-snapshot-query@1` | `test_osm_sync.py` pagination/filter characterization | complete |
| Geometry repair, multipolygon normalization, centroid and EPSG:25832 area | module SQL over immutable snapshot EWKB | module DB session; no Host table | SQL/import tests plus Host lifecycle | complete |
| Upsert by `(source, source_osm_type, source_osm_id)` | module `UPSERT_SQL` | none | existing UUID/slug reuse and duplicate-delivery test | complete |
| Preserve manual Wikidata decisions and mark conflicting OSM QIDs | module `UPSERT_SQL` | none | SQL characterization | complete |
| Removed OSM candidates | module retains historical no-delete behavior | none | SQL/no-delete characterization | complete |
| Parent reconciliation | module `PARENT_SQL` over `analysis_areas` | none | idempotent sync test | complete |
| OSM completion trigger | namespaced module subscriber | `osm.postprocessing-completed@1` | real Host event-bus dispatch plus registration check | complete |
| OSM cache invalidation | module sync transaction | `CacheGenerationPort.bump` | one bump for first sync, none for unchanged duplicate | complete; bumps historical `analysis-areas` and `analytics` resources |
| OSM pagination | module cursor loop, 500-item pages | `OsmSnapshotQueryPort` | advancing-cursor and page assertions | complete |
| Wikidata OSM-ID, Wikipedia and contextual search matching | module domain/application/provider | `ModuleContext.http`, module cache | provider and matching characterization | complete |
| Wikidata retry, provider error isolation and positive/negative caching | module provider policy | `HttpClientFactoryPort` | timeout/retry/error/cache tests | complete; no direct `httpx` fallback |
| Wikidata bulk persistence | module short write phase | DB plus `CacheGenerationPort.bump` | one bump for 1+ writes, none for zero writes | complete |
| Manual Wikidata assignment | `analysis-areas.wikidata-maintenance@1` | HTTP, DB and generation port | validation and rollback tests | complete; row and generation roll back together |
| Scheduled Wikidata refresh | `analysis-areas.wikidata-refresh` | normal scheduler context | Host registration/lifecycle test | complete |
| Polygon spatial selection | Host read-only matcher resolved by module | `platform.polygon-spatial-match@1` | unit and real Host chain tests | complete |
| Polygon identity resolution | Host-owned batched UUID-to-integer-ID lookup | `platform.polygon-identity@1` | batch/missing/Host chain tests | complete |
| `polygon_analysis_areas` reconcile | module `PolygonAnalysisAreaReconciler` | module DB session and both Polygon contracts | create/update/delete/no-op/missing/rollback tests | complete |
| Optional social-change publication | foreign social domain | no public publication event contract | historical audit | not restored; normal OSM postprocess historically passed `publish_relevant_updates=False` |

## OSM semantics

The module requests bounded administrative-boundary and polygonal-place pages,
then interprets the generic tags itself. It preserves the historical rules:

- the municipality is the named administrative polygon with the smallest
  numeric `admin_level`, breaking ties by largest area;
- the next two contained administrative levels become district and quarter;
- `borough` and `suburb` places become districts, while `quarter` and
  `neighbourhood` become quarters unless the same OSM identity was already
  selected administratively;
- names prefer `name`, then `name:de`, then `OSM <id>`;
- source OSM type/ID, admin level, place, Wikidata/Wikipedia tags, geometry and
  import timestamp are persisted;
- conflict-key updates never replace UUID or slug; stale candidates are retained,
  matching the historical implementation;
- unchanged repeated snapshots perform no row write and no generation bump.

The event payload is used only as a trigger. The handler always reads the current
committed snapshot through the public service. At-least-once delivery therefore
converges on the same domain state.

## Transactions

OSM snapshot reads and module writes share a Host-managed session. Area and parent
mutations, Polygon matching, identity resolution and relation reconciliation are
followed by one transactional generation bump and the caller-owned commit. OSM
synchronization retains the historical `analysis-areas` and `analytics`
generation effects. An unchanged duplicate event performs no relation write and
no generation bump.

Wikidata uses three short phases: snapshot read and release, external HTTP without
a DB session, then a new write session. Bulk sync performs zero bumps for zero
writes and one bump for one or more writes. Manual assignment updates the row,
bumps `analysis-areas`, and commits in that order. Module-cache clearing is an
additional post-commit optimization, never a replacement for the shared bump.

## Polygon relation semantics

The stable Analysis Area UUID is the spatial request `external_id`. Historical
`area_type` values (`MUNICIPALITY`, `DISTRICT`, `QUARTER`) are the selection
groups, preserving the former smallest-covering-area-per-type behavior. Polygon
UUIDs from the matcher are resolved in one identity request. Desired state uses
the existing unique key `(polygon_id, analysis_area_id)` and preserves the
historical `POINT_ON_SURFACE` assignment and unrounded overlap ratio.

Complete results create missing rows, update changed overlap/type values, delete
stale rows and leave identical rows untouched. If any identity is missing, the
entire relation phase is a no-op and reports the missing UUIDs; no stale deletion
is inferred. The module reads no `user_polygons` table and imports no private Host
implementation.

## Operator path

Manual Wikidata assignment is production-reachable through the versioned
maintenance service. The Host still has no generic argument-bearing module CLI,
so a shell-friendly wrapper remains an operator-convenience gap rather than a
blocker for scheduled/event-driven production functionality.
