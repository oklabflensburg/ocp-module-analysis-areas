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
- [x] Existing module has no mutations, module permissions, settings, events or jobs;
  none were invented during extraction.
- [x] Built-in host code, migrations and tests were not deleted.
- [ ] Public service ports must replace the audited legacy adapter before the host
  can enforce a strict public-SDK-only external runtime.
- [x] Host migration adoption discovers the packaged history passively while the
  installed module is disabled, without runtime activation.
- [x] Normal Host cutover uses only
  `OCP_EXCLUDED_BUILTIN_MODULES=analysis-areas`; verify/install/enable/disable/
  re-enable, generated environment, frontend discovery, typecheck and build pass.
- [x] Missing cutover configuration fails fast for duplicate backend and frontend
  module IDs; duplicate Host/module migration revisions also fail fast.

The legacy backend adapter is classification **A** for this pinned host: it is a
compatibility layer over still-present generic/neighbor-domain Host services and
the installed runtime is technically functional without importing Built-in
`app.modules.analysis_areas` code. It remains an architectural blocker for a
strict public-SDK-only module because those service imports are private.
