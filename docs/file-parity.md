# File parity

Pinned Host: `open-city-planner@81844b666aca8356f9c5cb9a86f00cf15b784f79`
(merge commit of Host PR #193, Backend Module SDK 1.9.0).

## Backend

The module-owned files remain under `backend/src/ocp_module_analysis_areas/`.
The SDK 1.9 cutover introduced `api/filters.py`, `application/cache.py`,
`application/queries.py` and `settings.py`. It removed `integrations/legacy.py`,
`application/legacy_queries.py` and the unregistered `application/legacy_sync.py`.
The router is now created at registration time with explicit public ports.

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
- CLI consumers for OSM sync and Wikidata enrichment.

These are consumers, platform primitives, or other domain owners. Their behavior
remains covered by Host tests and no implementation was copied or relabeled.
