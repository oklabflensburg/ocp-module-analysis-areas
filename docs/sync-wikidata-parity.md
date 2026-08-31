# OSM/Wikidata parity inventory

Historical reference: `open-city-planner@81844b666aca8356f9c5cb9a86f00cf15b784f79`
(the pinned SDK 1.9.0 host contract). The inventory also follows each file back
through Git, in particular `4468b0414cff4370b96023eb2ff578b2f07f71fd`, which
moved the built-in into the module-shaped Host directory without changing these
workflows.

Classification: **A** is Analysis-Areas-owned, **B** is a generic Host
capability, **C** is another domain reached through a contract/event, and **D**
is proven obsolete. Nothing in this inventory is classified D.

| Historical function | Old path | Trigger | Tables | Provider | Cache effect | Historical tests | Class / new owner | External-module target / status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Discover municipality and infer district/quarter levels | `application/legacy_sync.py` | `sync_analysis_areas` CLI and OSM postprocess | read `osm_features` | OSM snapshot | none | `test_osm_sync.py`, SQL characterization in `test_analysis_areas.py` | A algorithm, C OSM snapshot | `application/sync.py`; **blocked** pending an OSM snapshot contract |
| Select administrative and polygonal-place candidates, repair/multipolygon geometry, calculate centroid/area | same | same | read `osm_features` | OSM snapshot | none | `test_osm_sync.py`, `test_analysis_areas_characterization.py` | A algorithm, C OSM snapshot | same blocker; direct foreign-table SQL is forbidden |
| Upsert by `(source, source_osm_type, source_osm_id)` while preserving UUID/slug and manual Wikidata decisions | same | same | write `analysis_areas` | none | later invalidation | SQL characterization in `test_analysis_areas.py` | A | port after the immutable OSM snapshot exists |
| Reconcile removed upstream areas | no deletion existed in `legacy_sync.py` | same | `analysis_areas` | OSM snapshot | none | no deletion test existed | A | historical behavior is retain-not-delete; must remain explicit in the port |
| Rebuild polygon-to-area assignment | same | same | `polygon_analysis_areas`, read `user_polygons` | Polygon domain | analytics invalidation | characterization coverage | A relation, C polygon geometry | blocked pending a polygon-assignment command contract; foreign ORM/table access is forbidden |
| Publish relevant area changes | same via `enqueue_area_publication` | optional CLI flag; disabled in OSM postprocess | social outbox plus area read | social publishing | none | social publishing tests | C | use a versioned domain event after commit; exact event consumer contract is missing |
| Invalidate `analysis-areas` and `analytics` generations | same | end of sync | `cache_versions` | cache platform | generation bump | cache/API tests | B | SDK 1.9 exposes only `current`; mutating invalidation contract is missing |
| Resolve OSM Wikidata, OSM Wikipedia, then contextual search | `services/wikidata_enrichment.py` | sync CLI, sync-with-enrichment CLI, OSM postprocess | read/write `analysis_areas` | Wikidata API | provider cache and analysis-area invalidation | `test_wikidata_enrichment.py` | A using B HTTP/cache/DB | `integrations/wikidata.py`, `application/wikidata.py` |
| Validate candidates by name, geographic distance, parent and description | same | same | area snapshot | Wikidata API | provider cache | same | A | same; network phase uses immutable snapshots and no checked-out DB session |
| Persist status/confidence and preserve `MANUAL` rows | same | same | `analysis_areas` | none | module cache clear; shared generation bump unavailable | historical SQL behavior plus ported tests | A using B cache invalidation | implementation ready through maintenance service; automatic execution blocked |
| Manual assignment by slug or unique case-insensitive name, QID/entity/name validation | `cli/set_area_wikidata.py` | operator CLI | `analysis_areas` | Wikidata API | module cache clear; shared generation bump unavailable | previously indirect | A | public maintenance service; generic argument-bearing module CLI and transactional generation bump contracts are missing |
| Wikidata retries, timeout/provider error isolation and negative caching | `services/wikidata_enrichment.py` | every enrichment | none during HTTP | Wikidata API | positive/negative TTL | provider tests | A policy using B HTTP/cache | ported; public HTTP port preferred; temporary trusted-module `httpx` fallback has explicit timeout/User-Agent, bounded retry and cleanup tests because the pinned production context leaves `http` unwired |
| Structured job logging/metrics/retry/non-concurrency | Host job registry | registered job | none | none | none | `test_module_jobs.py` | B | application implementation exists, but `analysis-areas.wikidata-refresh` is intentionally **not registered** until transactional shared-generation invalidation is public |
| OSM postprocessing trigger | `cli/postprocess_osm.py` immediately after OSM reconciliation, inside its transaction for area sync and after commit for Wikidata | hourly OSM import | OSM, area, polygon, state tables | OSM/Wikidata | several generations | `test_osm_sync.py` | C event producer, A subscribers/jobs | **blocked**: the pinned Host emits no public postprocess event |
| Operational CLIs | three files under `backend/app/cli/` | operator invocation | as above | OSM/Wikidata | as above | no direct CLI tests | A commands over B generic module operations | maintenance service exists; generic job-run and argument-bearing command contracts are missing |

## Transaction and failure characterization

- OSM postprocessing called area sync with `commit=False`, then refreshed OSM
  polygon sources, bumped Host generations, updated replication state and made
  one commit. Standalone sync defaulted to one commit of its own.
- Removed OSM candidates were not deleted from `analysis_areas`; the only
  deletion in the postprocessor reconciled `osm_features`.
- Area identity was stable because the upsert conflict key was OSM identity and
  updates did not overwrite `uuid` or `slug`.
- Wikidata bulk enrichment caught failures per area, recorded only the exception
  type, continued, then called `bump_cache_versions(session,
  ("analysis-areas",))` exactly once after the loop and before the single
  `session.commit()` (even when the selection was empty). Manual assignment
  likewise updated the row, bumped exactly `analysis-areas`, and then committed.
  Thus each data change and its generation update shared one transaction; no
  `analytics` generation was bumped by either Wikidata path.
- The external module's `CachePort.clear()` maps to the Host's module-prefixed
  `delete_pattern` and therefore clears only `...:module:analysis-areas:*`. It
  runs after a committed write (and only when bulk sync resolved rows), never as
  a Host-wide Redis flush. This scoped clear does not replace the missing shared
  generation bump.
- The old implementation kept its ORM session checked out during every network
  request. The external implementation intentionally improves this production
  property: snapshot read, released session, HTTP resolution, short write.
- Candidate-distance parity is semantic rather than byte-level: the old
  `ST_DistanceSphere` and the released-session haversine calculation use the same
  coordinates and thresholds; their Earth-radius difference is far below the
  stored two-decimal confidence precision.

## Required Host follow-ups

The smallest sufficient public additions are:

1. A versioned OSM snapshot/query service returning immutable area-candidate
   DTOs plus an `osm.postprocessing-completed` event emitted after the OSM
   transaction commits. The module subscribes and schedules its own sync; the
   Host never names Analysis Areas.
2. A cache-generation invalidation operation (`bump(session, resources)`) on the
   existing generic port. It must participate in the caller transaction. Until
   that contract exists, the automatic Wikidata job remains unregistered even
   though the implementation and maintenance service are available.
3. A polygon-domain command that atomically refreshes assignments for a supplied
   module-owned area snapshot/scope, or a versioned event consumed by the polygon
   owner. No `user_polygons` table/ORM type may cross the boundary.
4. A generic operational CLI capable of listing/running registered jobs and, for
   manual maintenance, invoking validated module command definitions with
   arguments. The existing installer CLI does not expose `JobRunner`.
5. Wire the existing `HttpClientFactoryPort` into the production `ModuleContext`
   so Host-owned timeout, telemetry and egress policies replace the explicitly
   documented module-owned fallback.

Until those contracts exist, implementing OSM sync or claiming postprocessing
parity would require private table/implementation coupling and would violate
Issue #5's acceptance boundary. These are blocking parity gaps, not obsolete
functions.
