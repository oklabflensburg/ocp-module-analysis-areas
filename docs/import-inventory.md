# Import inventory

Pinned contract: `open-city-planner@81844b666aca8356f9c5cb9a86f00cf15b784f79`,
Backend Module SDK `1.9.0`.

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

The earlier extraction deleted `application/legacy_sync.py` because it had no
runtime registration inside the built-in module. Git history proves that Host CLI
and OSM postprocessing consumers nevertheless existed. Its reinstatement is
blocked on the public OSM, polygon-command, cache-mutation and postprocessing-event
contracts inventoried in `sync-wikidata-parity.md`; no private replacement import
was introduced.

Wikidata enrichment uses `ModuleContext.database`, `.cache`, `.settings` and
`.services`. It prefers `ModuleContext.http` when supplied. SDK 1.9 defines that
port but the pinned production context does not wire it, so the trusted
in-process provider adapter temporarily has an explicit `httpx`
timeout/User-Agent/bounded-retry fallback with context-managed cleanup, without
importing Host implementation. Host-owned HTTP-client infrastructure remains the
architectural target. The scheduler is deliberately unused until the public
cache-generation port gains a transactional mutation operation.

`backend/tests/test_contracts.py` rejects every `app.*` import other than
`app.platform.modules.sdk` and rejects legacy files in the built wheel. The pinned
Host's `scripts/check_external_module_imports.py` is also run against the extracted
wheel.

**Private Host backend imports: 0.**
