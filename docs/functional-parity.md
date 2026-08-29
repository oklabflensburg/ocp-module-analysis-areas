# Functional parity checklist

- [x] Public list, UUID lookup, slug detail, GeoJSON and sitemap routes retained.
- [x] Preview WebP, ETag/304/cache headers and error mapping retained.
- [x] Polygon list, analytics, comparison, statistics and time-series routes retained.
- [x] PostGIS geometries, SRID 4326, spatial POI query and response limits retained.
- [x] OSM provenance, Wikidata/Wikipedia links and POI map navigation retained.
- [x] `/gebiete` and `/gebiete/:slug`, SSR/SEO/structured data retained.
- [x] Navigation, map source/layers, selection and feature info retained.
- [x] Analysis components, API composable, store and public types retained. Map
  layer controls, selection presentation, external links and statistics use the
  public frontend SDK and ship in the installable layer. The separately rendered
  detail map remains explicitly classified as Host compatibility.
- [x] Existing table names/data adoption and historical revisions retained.
- [x] Existing module has no mutations, module permissions, events or jobs. Its two
  cache TTLs are validated, namespaced module settings with existing defaults.
- [x] Built-in host code, migrations and tests were not deleted.
- [x] Public service ports replace the legacy adapter; the installable backend is
  strict public-SDK-only module code.
- [x] Host migration adoption discovers the packaged history passively while the
  installed module is disabled, without runtime activation.
- [x] Normal Host cutover uses only
  `OCP_EXCLUDED_BUILTIN_MODULES=analysis-areas`; verify/install/enable/disable/
  re-enable, generated environment, frontend discovery, typecheck and build pass.
- [x] Missing cutover configuration fails fast for duplicate backend and frontend
  module IDs; duplicate Host/module migration revisions also fail fast.

Host Issue #192 is technically fulfilled for the backend contract. PR #2 remains
open for review and frontend Issue #4 (`AnalysisAreaDetailMap`) remains the known
hidden Host-frontend dependency.
