# Analysis Areas for Open City Planner

Standalone full-stack OCP module extracted losslessly from the built-in
`analysis-areas` module in
[`oklabflensburg/open-city-planner`](https://github.com/oklabflensburg/open-city-planner).

Version `1.0.0` was extracted from host commit
`b8c4db7f3246d21c53a1b5633915be16bb84a633` on
`staging/epic-91-modular-host`. This repository is the future source of truth;
the built-in remains in the host until the explicit cutover and is not deleted by
this issue.

## Contents

- Python distribution `ocp-module-analysis-areas`, namespace
  `ocp_module_analysis_areas`, entry point
  `open_city_planner.modules / analysis-areas`;
- Nuxt layer package `@open-city-planner/analysis-areas` with `/gebiete`, detail,
  SEO/SSR, statistics, POI navigation and map contributions, plus explicitly
  retained host-compatibility components/store pending public SDK contracts;
- immutable copies of the relevant productive migration history;
- preserved host characterization/E2E tests and standalone contract tests;
- pinned host builder, verifier and lifecycle integration test.

## Development

Requirements are Python 3.12.14, uv 0.12.5, Node 22.23.2 and pnpm 11.22.0.

```bash
cd backend
uv sync --frozen --extra dev
uv run ruff check src tests
uv run pytest
uv build --wheel

cd ../frontend
corepack pnpm install --frozen-lockfile
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
```

Prepare and test the exact host contract:

```bash
scripts/prepare-host-contract
scripts/build-bundle
scripts/host-contract-test
```

The resulting files are `dist/analysis-areas-1.0.0.ocp` and its `.sha256`.
The `.ocp` is built by the pinned host's v1 builder, not by repository-local ZIP
code.

## Installation and cutover

After the built-in with the same ID has been removed from host discovery:

```bash
cd open-city-planner/backend
uv run python -m app.cli.modules verify analysis-areas-1.0.0.ocp
uv run python -m app.cli.modules install analysis-areas-1.0.0.ocp
uv run python -m app.cli.modules enable analysis-areas
```

Install defaults to disabled. Disable/re-enable preserves the installed wheel,
frontend package, tables and packaged migration history.

The pinned host currently rejects `verify` before inspecting the package whenever
the built-in ID still exists. `scripts/host-contract-test` therefore models the
documented cutover in a scoped test: it removes only built-in discovery, then runs
the real host verifier/installer and enable/disable/re-enable preflights. It always
restores the checkout.

## Compatibility and known prerequisites

The initial standalone release deliberately keeps the source module's narrow
legacy adapter so statistics, polygons, caching, preview security, POI analytics
and social publication behavior are not lost. The import baseline prevents it
from expanding. Public host service contracts must replace these internal imports
before a strict SDK-only production cutover.

Existing Alembic IDs and their host-chain `down_revision` links are not renamed.
The current external migration contract only accepts new `mod_analysis_areas_*`
revisions, so the adopted history is packaged but remains host-executed until the
host supports adopted historical revisions. No baseline table creation or data
copy was introduced.

Detailed evidence:

- [file parity](docs/file-parity.md)
- [test parity](docs/test-parity.md)
- [migration inventory](docs/migration-inventory.md)
- [import inventory](docs/import-inventory.md)
- [functional parity](docs/functional-parity.md)

## Host pin updates

`.github/ocp-host-contract.json` is the only pin source. Update it only to a
reviewed full commit SHA, rerun every standalone and host-contract gate, update
the extraction/parity notes if contracts changed, and commit the pin together
with those results. Never point CI at a branch name.

## Release

Tag `v1.0.0` must equal manifest, backend and frontend version. The release job
reruns all gates, builds the `.ocp`, calculates SHA-256 and refuses to mutate an
existing release. Release note: “First standalone release extracted from Open
City Planner built-in module.”

## Cutover preconditions

Do not remove the built-in until standalone CI, v1.0.0 release, registry artifact
verification, install/lifecycle, migration and existing-data compatibility, API,
frontend and E2E parity are confirmed. Never activate built-in and external
`analysis-areas` simultaneously.

License: AGPL-3.0-only. OpenStreetMap-derived data remains subject to ODbL.
