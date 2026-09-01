# File parity

Pinned Host: `open-city-planner@e1d7921698bb030f9e01de9ad16a9d85cb334b26`
(merge commit of Host PR #205, Backend Module SDK 1.12.0).

## Backend

The module-owned files remain under `backend/src/ocp_module_analysis_areas/`.
The SDK cutover introduced `api/filters.py`, `application/cache.py`,
`application/queries.py` and `settings.py`. It removed `integrations/legacy.py`
and `application/legacy_queries.py`. The earlier removal of
`application/legacy_sync.py` is replaced by the public-contract-only
`application/osm_sync.py`. Wikidata domain values, provider integration and application
workflow live in `domain/wikidata.py`, `integrations/wikidata.py` and
`application/wikidata.py`. The router is created at registration time with
explicit public ports.

The four files under
`backend/src/ocp_module_analysis_areas/migrations/history/` remain byte-identical
to the pinned Host copies for `20260814_0014`, `20260817_0023`,
`20260818_0025`, and `20260819_0032`.

## Installable frontend layer

`frontend/module.json` and all original files in the Host Built-in Nuxt layer are
represented under `frontend/layer/`. The Store, routes, API/SEO composables,
types, overview utility and map runtime already used public contracts.

The #186/#191 Host state makes the following additional module-owned sources
public-contract-compatible, so they now ship in the installable layer:

- `AnalysisAreaCard.vue` through `useMapSelectionPort`;
- `AnalysisAreasLayerControls.vue` through the public `map.layers` UI slot;
- `AreaStatistics.vue` through `OcpStatusBadge`;
- `ExternalSourceLink.vue` through `ExternalProvider` and `OcpProviderIcon`;
- `AreaExternalLinks.vue`, which composes the module-owned external-link UI.
- `AnalysisAreaDetailMap.vue`, which owns the standalone detail-map instance and
  uses the public style, HTTP and cursor ports. Its direct MapLibre runtime import
  is declared by the frontend package at the Host-compatible `6.4.1` version.

The manifest now declares the map runtime, map-layer controls and selection
presentation contributions. `/gebiete` and `/gebiete/:slug` remain the two
module routes.

## Remaining `frontend/host-compatibility` audit

These preserved sources are not included in the npm package:

| Files | Classification | Reason |
| --- | --- | --- |
| `ComparableList.vue`, `PolygonStatistics.vue` | Fachlich nicht Analysis-Areas-owned | Polygon/comparison stores, types, routes and OSM polygon details belong to neighboring domains. |
| `DistributionCharts.vue`, `FastFacts.vue`, `FastFactsEditor.vue`, `IndustryChart.vue`, `MarketBenchmarks.vue`, `RentTable.vue` | Noch Host-private und fachlich Analytics/administration-owned | They depend on private analytics, filter, map, OSM or administration stores and shared chart/metric utilities. Copying those domains would falsely relabel ownership. |
| `LocationAnalysis.vue` | Noch Host-private and polygon-analysis-owned | It consumes the Host API client and `~/types/analytics`, not an Analysis Areas public port. |
| `ViewportOsmSummary.vue` | Noch Host-private and OSM-owned | It depends on the private OSM viewport store and Host industry/OSM label utilities. |

No remaining file became safely movable merely through the new cutover setting.
The six public-contract-compatible, module-owned components listed above were
moved; no Analytics, Polygon, OSM, notification or comparison implementation was
copied or renamed as Analysis Areas code.

## Intentionally Host-only

- central router/runtime, AppShell, navigation renderer, MapCanvas and module host;
- DB session implementation and cache/preview/security/statistics/polygon adapters;
- `/vergleich` and comparison stores/components;
- polygon UI/models, notification UI, OSM viewport store and statistics storage;
- Statistics migration `20260816_0016` and all unrelated Host-chain migrations;
- generic argument-bearing module-operation CLI convenience;
- Polygon UUID-to-internal-scope resolution, documented in
  `sync-wikidata-parity.md`.

These are consumers, platform primitives, or other domain owners. Wikidata
behavior and OSM area synchronization are now module-owned; the remaining polygon
relation blocker is explicit and no private implementation was copied or relabeled.
