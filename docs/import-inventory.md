# Import inventory

Pinned contract: `open-city-planner@e1d7921698bb030f9e01de9ad16a9d85cb334b26`,
Backend Module SDK `1.12.0`.

| Standalone code | Imported surface | Status |
| --- | --- | --- |
| `module.py`, API and application layer | `app.platform.modules.sdk` | documented public SDK only |
| `persistence/models.py` | SQLAlchemy/GeoAlchemy | module-owned persistence models and metadata |
| API schemas and filter parser | Pydantic/FastAPI | module-owned response and HTTP contracts |
| Nuxt layer | `#frontend-module-sdk`, `#frontend-module-sdk/ui` | public frontend contracts |
| Detail map | `maplibre-gl` 6.4.1 | direct declared package dependency; style, HTTP and cursor remain public Host ports |
| remaining compatibility sources | private frontend stores/types/components owned by Analytics, Polygon, OSM and neighboring domains | excluded from the installable frontend package; see `file-parity.md` |

The former `integrations/legacy.py` adapter was deleted. Its replacements are:

- `app.db.session.get_session` → `ModuleContext.database`;
- Host cache service/keys → `ModuleContext.cache` plus stable relative module keys;
- cache versions → `ModuleContext.cache_generations`;
- public query guard/settings → `ModuleContext.public_queries` and its immutable limits;
- map preview service → `ModuleContext.map_previews` and SDK preview DTOs/errors;
- polygon ORM/private analytics helpers → module-owned `PolygonAnalysisArea` lookup,
  `PolygonScope`, `ModuleContext.polygons` and `ModuleContext.polygon_analytics`;
- Statistics services/schemas → `ModuleContext.statistics`, SDK DTOs and module-owned
  public response schemas;
- Host GeoJSON, external-link, analytics and polygon-filter schemas → module-owned schemas;
- Host POI category SQL → module-owned `AREA_POI_CATEGORY_SQL`.

The earlier `application/legacy_sync.py` is replaced by `application/osm_sync.py`.
It reads immutable, paginated OSM snapshots through
`platform.osm-snapshot-query@1`, writes only module-owned tables and subscribes to
`osm.postprocessing-completed@1`.

The internal Wikidata enrichment implementation is written against public
`DatabaseSessionProvider`, `CachePort`, `CacheGenerationPort` and required
`HttpClientFactoryPort` contracts. The installable provider contains no direct
`httpx` import. The scheduler and service registry expose safe refresh and manual
maintenance paths.

`backend/tests/test_contracts.py` rejects every `app.*` import other than
`app.platform.modules.sdk` and rejects legacy files in the built wheel. The pinned
Host's `scripts/check_external_module_imports.py` is also run against the extracted
wheel.

**Private Host backend imports: 0.**
