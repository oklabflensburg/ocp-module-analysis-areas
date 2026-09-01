# Test parity

The extraction found 21 directly relevant host test/fixture files containing 86
test cases (47 backend, 39 frontend) and preserves all 21 files under
`tests/host-baseline`. Standalone runners add focused backend and frontend
contract/characterization coverage, including the ported Wikidata cases. No
source test was deleted from the host. Full-host cases keep their original host
runner; standalone cases run directly in this repository.

Polygon relation coverage includes create, changed-overlap update, stale delete,
unchanged second run, duplicate-event convergence, multiple selection groups,
single batched identity lookup, missing-identity fail-safe, transactional rollback
and the real pinned-Host spatial-match → identity → module persistence chain.

| Host test | Standalone status |
| --- | --- |
| `backend/tests/modules/analysis_areas/test_analysis_areas_module.py` | preserved snapshot; identity/persistence/import behavior also covered by standalone backend contracts and pinned-host verifier |
| `test_analysis_areas_characterization.py`, `test_analysis_area_public_api.py` | preserved; route set characterized locally |
| `test_analysis_areas.py`, `test_analysis_area_analytics_performance.py` | preserved; executed in full host/PostGIS environment |
| `test_flensburg_statistics.py`, `test_osm_sync.py` | preserved cross-domain compatibility plus standalone pagination/upsert/idempotency coverage |
| `test_wikidata_enrichment.py` | matching, provider, cache, error, idempotency and released-session behavior ported to `backend/tests/test_wikidata.py` |
| `analysis-areas-module.test.ts` | preserved; routes/navigation/map definitions covered locally and by host frontend preflight |
| `analysis-area-overview*.test.ts`, `analysis-area-pages.test.ts`, `analysis-areas-ui.test.ts`, `area-poi-navigation.test.ts`, `area-statistics.test.ts` | preserved; core source/UI contracts covered locally; SSR cases remain host-run |
| four `area-*.spec.ts` E2E files | preserved; remain host Playwright tests because they require the full application and seeded database |
| two frontend fixtures | preserved with their tests |

Broader host tests discovered through consumer imports (assistant, search,
polygons, social publishing, sitemap, map selection, Redis and notifications)
remain intentionally in the host suite. They test their owning domains consuming
Analysis Areas rather than module-owned code; the source repository is not
modified by this issue.
