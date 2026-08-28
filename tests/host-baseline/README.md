# Preserved host characterization suite

These files are byte-for-byte snapshots from
`open-city-planner@b8c4db7f3246d21c53a1b5633915be16bb84a633`. They are retained so
the extraction cannot silently discard host-level API, persistence, SSR, GIS,
statistics, POI, OSM, Wikidata, and E2E coverage.

They are intentionally not collected by the standalone package test runners:
they require the complete host application, its fixtures, PostGIS, and browser
harness. The pinned host contract job remains their execution environment. See
`docs/test-parity.md` for the mapping and status.
