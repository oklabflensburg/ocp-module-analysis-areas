# Functional parity checklist

- [x] Public list, UUID lookup, slug detail, GeoJSON and sitemap routes retained.
- [x] Preview WebP, ETag/304/cache headers and error mapping retained.
- [x] Polygon list, analytics, comparison, statistics and time-series routes retained.
- [x] PostGIS geometries, SRID 4326, spatial POI query and response limits retained.
- [x] OSM provenance, Wikidata/Wikipedia links and POI map navigation retained.
- [x] `/gebiete` and `/gebiete/:slug`, SSR/SEO/structured data retained.
- [x] Navigation, map source/layers, selection and feature info retained.
- [x] Analysis components, API composable, store and public types retained; only
  public-contract-compatible files are packaged, with the remainder preserved as
  explicit host compatibility sources.
- [x] Existing table names/data adoption and historical revisions retained.
- [x] Existing module has no mutations, module permissions, settings, events or jobs;
  none were invented during extraction.
- [x] Built-in host code, migrations and tests were not deleted.
- [ ] Public service ports must replace the audited legacy adapter before the host
  can enforce a strict public-SDK-only external runtime.
- [ ] Host cutover must remove the duplicate Built-in ID from backend and frontend
  discovery before the standard CLI can verify/install the external artifact.
- [ ] Host migration contract must support adopted historical revisions before
  the packaged history can become a disabled-module Alembic discovery source.
