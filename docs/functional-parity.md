# Functional parity checklist

- [x] Public list, UUID lookup, slug detail, GeoJSON and sitemap routes retained.
- [x] Preview WebP, ETag/304/cache headers and error mapping retained.
- [x] Polygon list, analytics, comparison, statistics and time-series routes retained.
- [x] PostGIS geometries, SRID 4326, spatial POI query and response limits retained.
- [x] OSM provenance, Wikidata/Wikipedia links and POI map navigation retained.
- [x] `/gebiete` and `/gebiete/:slug`, SSR/SEO/structured data retained.
- [x] Navigation, map source/layers, selection and feature info retained.
- [x] Analysis components, API composable, store and public types retained. Map
  layer controls, selection presentation, external links, statistics and the
  separately rendered detail map ship in the installable layer. The detail map
  uses public style/HTTP/cursor ports, declares MapLibre directly and preserves
  its browser-only lifecycle, resize cleanup and social-preview `@ready` event.
- [x] Existing table names/data adoption and historical revisions retained.
- [x] Wikidata lookup, matching, refresh and manual-assignment implementation is
  retained internally as module-owned domain, provider and application code.
- [ ] Automatic execution and public mutating maintenance exposure are
  intentionally disabled: the module registers neither
  `analysis-areas.wikidata-refresh` nor
  `analysis-areas.wikidata-maintenance` and announces no maintenance capability
  until a public transactional `CacheGenerationPort.bump(session, resources)`
  can preserve the historical `analysis-areas` generation contract.
- [x] Wikidata network calls run without a checked-out DB session and provider
  failures remain isolated per area.
- [ ] OSM area sync, polygon assignment refresh, social-change publication and
  the OSM postprocessing trigger require the public contracts documented in
  `sync-wikidata-parity.md`; complete functional parity is not yet claimed.
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

Host Issue #192 and module Issue #4 are technically fulfilled. PR #2 remains
open for final review; the hidden Host `AnalysisAreaDetailMap` auto-import
dependency is removed.
