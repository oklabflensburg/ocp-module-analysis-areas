# File parity

Source commit: `b8c4db7f3246d21c53a1b5633915be16bb84a633`.

## Backend

Every file below moved from `backend/app/modules/analysis_areas/` to
`backend/src/ocp_module_analysis_areas/` with the same relative suffix:

`__init__.py`, `api/{__init__,router,schemas}.py`,
`application/{__init__,legacy_queries,legacy_sync,query_service}.py`,
`contracts/__init__.py`, `domain/{__init__,models}.py`,
`integrations/{__init__,legacy}.py`, `module.py`, and
`persistence/{__init__,models}.py`.

Status: übernommen. Refactors are limited to namespace imports, distribution and
frontend package identity, and the module-local declarative base.

Historical migrations map from `backend/alembic/versions/<revision>.py` to
`backend/src/ocp_module_analysis_areas/migrations/history/<revision>.py` for
`20260814_0014`, `20260817_0023`, `20260818_0025`, and `20260819_0032`.

## Frontend

`frontend/frontend-modules/analysis-areas/module.json` maps to
`frontend/module.json`; all files under its `layer/` map to `frontend/layer/`.
Additionally, the complete `frontend/app/components/analysis/` directory plus
`useAnalysisAreaApi.ts`, `useAnalysisAreaSeo.ts`, `analysisAreas.ts`, and
`analysisArea.ts` are retained. Files accepted by the public module import guard
live in the installable layer. Files that still require private host primitives
live under `frontend/host-compatibility/` and are deliberately excluded from the
artifact until the corresponding public frontend contracts exist.

## Intentionally host-only

- central router/runtime, AppShell, navigation renderer, MapCanvas and module host;
- DB session implementation, cache/preview/security adapters and global settings;
- `/vergleich` and comparison store/components (Analytics/Comparison ownership);
- polygon UI/models, notification UI, OSM viewport store and statistics storage;
- Statistics migration `20260816_0016` and all unrelated host-chain migrations;
- CLI consumers for OSM sync and Wikidata enrichment.

These are consumers, public/platform primitives, or other domain owners. Their
behavior remains covered by preserved host tests and no implementation was copied
or relabeled as module-owned.
