# OSM/Wikidata parity matrix

Historical implementation reference: `open-city-planner@4468b0414cff4370b96023eb2ff578b2f07f71fd^`.
Current production contract: `open-city-planner@e1d7921698bb030f9e01de9ad16a9d85cb334b26`,
Backend Module SDK `1.12.0`.

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
| Polygon spatial selection | Host read-only matcher resolved by module | `platform.polygon-spatial-match@1` | Host service-resolution check | contract available |
| `polygon_analysis_areas` reconcile | remains module-owned | missing public UUID-to-internal-ID lookup | architecture/import guards | **blocked** |
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
mutations are followed by one transactional generation bump and the caller-owned
commit. OSM synchronization retains the historical `analysis-areas` and
`analytics` generation effects.

Wikidata uses three short phases: snapshot read and release, external HTTP without
a DB session, then a new write session. Bulk sync performs zero bumps for zero
writes and one bump for one or more writes. Manual assignment updates the row,
bumps `analysis-areas`, and commits in that order. Module-cache clearing is an
additional post-commit optimization, never a replacement for the shared bump.

## Exact remaining blocker

`platform.polygon-spatial-match@1` returns canonical Polygon UUID strings. The
adopted `polygon_analysis_areas.polygon_id` foreign key and public `PolygonScope`
use the Host's internal positive integer Polygon IDs. `PolygonQueryPort` only
lists projections for an already-known integer scope; it has no UUID lookup.

Consequently the module cannot persist desired matches without directly reading
`user_polygons`, which is forbidden. It also cannot safely change the adopted
relation to UUIDs because existing query and analytics ports require integer
scopes. The smallest missing generic contract is a read-only stable Polygon UUID
to internal `PolygonScope` ID resolver (or equivalent relation-safe token that
the existing public query/analytics ports accept).

No `user_polygons` ORM/SQL fallback is present. Until that generic contract is
available, Polygon match resolution is verified at registration, but relation
mutation is deliberately not executed or claimed.

## Operator path

Manual Wikidata assignment is production-reachable through the versioned
maintenance service. The Host still has no generic argument-bearing module CLI,
so a shell-friendly wrapper remains an operator-convenience gap rather than a
blocker for scheduled/event-driven production functionality.
