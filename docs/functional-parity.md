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
- [x] `analysis-areas.wikidata-refresh` and
  `analysis-areas.wikidata-maintenance@1` are registered. Wikidata mutations and
  the `analysis-areas` generation bump share one transaction.
- [x] Wikidata network calls run without a checked-out DB session and provider
  failures remain isolated per area.
- [x] OSM area sync is module-owned, paginated and triggered by
  `osm.postprocessing-completed@1`; duplicate delivery is idempotent.
- [ ] Polygon assignment persistence remains blocked because the spatial-match
  result exposes stable Polygon UUIDs while the adopted relation and public
  `PolygonScope` require internal integer IDs. No public UUID lookup exists.
- [ ] Optional historical social-change publication is not restored; the normal
  OSM postprocess path historically disabled it, so production synchronization is
  unaffected.
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

The only required Issue #5 blocker identified by this implementation is the
Polygon UUID-to-internal-ID mapping contract described above. A generic manual
operator CLI remains a convenience gap; manual mutation is safely available
through the versioned maintenance service.
