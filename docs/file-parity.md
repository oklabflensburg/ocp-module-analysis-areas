# File parity

Pinned Host: `open-city-planner@5e0357952ea1e8cac56076f64ec975530e6ab019`
(merge commit of Host PR #191).

## Backend

Every file below maps from `backend/app/modules/analysis_areas/` to
`backend/src/ocp_module_analysis_areas/` with the same relative suffix:

`__init__.py`, `api/{__init__,router,schemas}.py`,
`application/{__init__,legacy_queries,legacy_sync,query_service}.py`,
`contracts/__init__.py`, `domain/{__init__,models}.py`,
`integrations/{__init__,legacy}.py`, `module.py`, and
`persistence/{__init__,models}.py`.

Status: übernommen. Refactors are limited to namespace imports, distribution and
frontend package identity, and the module-local declarative base. The private
imports isolated in `integrations/legacy.py` are inventoried separately.

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

The manifest now declares the map runtime, map-layer controls and selection
presentation contributions. `/gebiete` and `/gebiete/:slug` remain the two
module routes.

## Remaining `frontend/host-compatibility` audit

These preserved sources are not included in the npm package:

| Files | Classification | Reason |
| --- | --- | --- |
| `AnalysisAreaDetailMap.vue` | Teilweise öffentlich, noch Host-private | Style, HTTP and cursor use public ports, but the component still imports `maplibre-gl` directly; installed layers outside the Host tree cannot resolve that private build dependency. |
| `ComparableList.vue`, `PolygonStatistics.vue` | Fachlich nicht Analysis-Areas-owned | Polygon/comparison stores, types, routes and OSM polygon details belong to neighboring domains. |
| `DistributionCharts.vue`, `FastFacts.vue`, `FastFactsEditor.vue`, `IndustryChart.vue`, `MarketBenchmarks.vue`, `RentTable.vue` | Noch Host-private und fachlich Analytics/administration-owned | They depend on private analytics, filter, map, OSM or administration stores and shared chart/metric utilities. Copying those domains would falsely relabel ownership. |
| `LocationAnalysis.vue` | Noch Host-private and polygon-analysis-owned | It consumes the Host API client and `~/types/analytics`, not an Analysis Areas public port. |
| `ViewportOsmSummary.vue` | Noch Host-private and OSM-owned | It depends on the private OSM viewport store and Host industry/OSM label utilities. |

No remaining file became safely movable merely through the new cutover setting.
The five public-contract-compatible, module-owned components listed above were
moved; no Analytics, Polygon, OSM, notification or comparison implementation was
copied or renamed as Analysis Areas code.

## Intentionally Host-only

- central router/runtime, AppShell, navigation renderer, MapCanvas and module host;
- DB session implementation, cache/preview/security adapters and global settings;
- `/vergleich` and comparison stores/components;
- polygon UI/models, notification UI, OSM viewport store and statistics storage;
- Statistics migration `20260816_0016` and all unrelated Host-chain migrations;
- CLI consumers for OSM sync and Wikidata enrichment.

These are consumers, platform primitives, or other domain owners. Their behavior
remains covered by Host tests and no implementation was copied or relabeled.
