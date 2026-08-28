# Import inventory

| Standalone code | Imported host surface | Class | Status |
| --- | --- | --- | --- |
| `module.py`, `application/query_service.py` | `app.platform.modules.sdk` | A — Public Module SDK | retained public contract |
| `persistence/models.py` | SQLAlchemy/GeoAlchemy only | C — platform-neutral primitive | host `Base` replaced by module-local declarative base |
| `integrations/legacy.py` | `app.cache.*`, `app.db.session` | C/D — host adapters/internal implementation | exact audited compatibility baseline; follow-up required |
| `integrations/legacy.py` | `app.core.config` | D — forbidden host settings internal | preserved only to prevent settings/limit behavior loss; guard forbids expansion |
| `integrations/legacy.py` | `app.models.user_polygon`, `app.schemas.*`, `app.services.analytics`, `area_statistics`, `poi_categories`, `social_publishing` | D/E — host internals/other domains | preserved compatibility boundary from the source module; requires public service contracts before cutover |
| Nuxt layer | `#frontend-module-sdk` | A — Public Frontend/Map SDK | retained |
| copied Analysis Areas store/components | `~/stores/map`, `~/utils/*`, shared types/components | B/C/E — host frontend contracts and neighboring domains | retained build-time host dependencies; no host code copied |

Changed imports:

- `app.modules.analysis_areas.*` became `ocp_module_analysis_areas.*` or relative imports.
- `app.db.base.Base` became a module-local SQLAlchemy `DeclarativeBase`; exported
  metadata and physical table names remain unchanged.
- copied module-owned frontend files reference their own `analysisArea` type via
  layer-relative imports. Public SDK imports are otherwise unchanged.

`backend/tests/test_contracts.py` fails on any new `app.*` import outside the
public SDK and the exact legacy adapter baseline. No legacy allowlist entry may be
added without updating this report and the host follow-up.
