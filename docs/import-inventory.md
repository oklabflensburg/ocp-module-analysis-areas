# Import inventory

| Standalone code | Imported host surface | Class | Status |
| --- | --- | --- | --- |
| `module.py`, `application/query_service.py` | `app.platform.modules.sdk` | A — Public Module SDK | retained public contract |
| `persistence/models.py` | SQLAlchemy/GeoAlchemy only | C — platform-neutral primitive | host `Base` replaced by module-local declarative base |
| `integrations/legacy.py` | `app.cache.*`, `app.db.session` | C/D — Host adapters/internal implementation | exact audited compatibility baseline; technically available in the pinned Host, but not public SDK |
| `integrations/legacy.py` | `app.core.config` | D — forbidden host settings internal | preserved only to prevent settings/limit behavior loss; guard forbids expansion |
| `integrations/legacy.py` | `app.models.user_polygon`, `app.schemas.*`, `app.services.analytics`, `area_statistics`, `poi_categories`, `social_publishing` | D/E — host internals/other domains | preserved compatibility boundary from the source module; requires public service contracts before cutover |
| Nuxt layer | `#frontend-module-sdk` | A — Public Frontend/Map SDK | retained |
| installable Analysis Areas store/components | `#frontend-module-sdk`, `#frontend-module-sdk/ui` | A — Public Frontend SDK | map, HTTP, SEO, selection, style, cursor and shared UI ports retained |
| remaining compatibility sources | private `~/stores/*`, `~/utils/*`, `~/types/*` and global components | D/E — Host-private/neighboring domains | excluded from package and classified in `file-parity.md`; no foreign domain copied |

Changed imports:

- `app.modules.analysis_areas.*` became `ocp_module_analysis_areas.*` or relative imports.
- `app.db.base.Base` became a module-local SQLAlchemy `DeclarativeBase`; exported
  metadata and physical table names remain unchanged.
- copied module-owned frontend files reference their own `analysisArea` type via
  layer-relative imports. Public SDK imports are otherwise unchanged.

`backend/tests/test_contracts.py` fails on any new `app.*` import outside the
public SDK and the exact legacy adapter baseline. No legacy allowlist entry may be
added without updating this report and the host follow-up.

## Exact private backend import inventory

All remaining private imports are confined to
`backend/src/ocp_module_analysis_areas/integrations/legacy.py`:

- `app.models.user_polygon.UserPolygon`;
- `app.services.analytics` (`_base_filters`, `_benchmark_metrics`, `_counts`);
- `app.services.area_statistics` (`area_statistic_series`, `area_statistics`);
- `app.services.cache_versions` (`cache_version`, `bump_cache_versions`);
- `app.services.map_previews` (`MapPreviewError`, `map_preview_service`);
- `app.services.poi_categories.AREA_POI_CATEGORY_SQL`;
- `app.services.public_query_security` (`guard_public_query`,
  `is_statement_timeout_error`);
- `app.services.social_publishing.enqueue_area_publication`;
- `app.schemas.analytics` (`BenchmarkMetrics`, `IndustryCount`);
- `app.schemas.external_links` (`ExternalLinks`, `WikidataExternalLink`,
  `WikipediaExternalLink`);
- `app.schemas.geojson.AreaGeometry`;
- `app.schemas.polygon_filters` (`PolygonFilterParams`,
  `polygon_filter_query`);
- `app.schemas.statistics` (`AreaStatisticSeriesRead`, `AreaStatisticsRead`);
- `app.cache.keys.build_cache_key`;
- `app.cache.service` (`cache_service`, `last_cache_status`);
- `app.db.session.get_session`.

Additionally, `app.core.config.get_settings` remains a private Host settings
import. There are no imports from `app.modules.analysis_areas`.

Classification for Host PR #191: **A**. The adapter is technically runnable as
an installed external module because it targets generic Host infrastructure and
still-present neighboring-domain services, not Built-in Analysis Areas code.
Nevertheless, it remains a merge/release risk for any requirement that external
modules use only stable public SDK surfaces; replacing these private imports is
still open work.
