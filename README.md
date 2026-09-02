# Analysis Areas for Open City Planner

Standalone full-stack OCP module extracted from the built-in
`analysis-areas` module in
[`oklabflensburg/open-city-planner`](https://github.com/oklabflensburg/open-city-planner).

Version `1.5.0` consumes the required Statistics query service through the public
service registry and targets Module SDK `>=1.15.0,<2.0.0`. This repository is the
source of truth; the Slim Host contains no built-in Analysis Areas runtime.

## Contents

- Python distribution `ocp-module-analysis-areas`, namespace
  `ocp_module_analysis_areas`, entry point
  `open_city_planner.modules / analysis-areas`;
- Nuxt layer package `@open-city-planner/analysis-areas` with `/gebiete`, detail,
  SEO/SSR, statistics, POI navigation and map contributions; module-owned UI
  uses the public frontend SDK while unrelated compatibility sources stay unpackaged;
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

The resulting files are `dist/analysis-areas-1.5.0.ocp` and its `.sha256`.
The `.ocp` is built by the pinned host's v1 builder, not by repository-local ZIP
code.

## Wikidata operations

The module registers `analysis-areas.wikidata-maintenance@1` and the scheduled
`analysis-areas.wikidata-refresh` job. Both use `ModuleContext.http` exclusively.
Reads, provider calls and writes use separate phases, so Wikidata latency never
retains a checked-out DB session. Every mutation calls
`CacheGenerationPort.bump(session, ("analysis-areas",))` before the caller-owned
commit; rollback therefore covers the row and generation together.

The versioned maintenance service is the safe programmatic manual-assignment
path. A generic argument-bearing operator CLI remains a convenience gap.

## Installation and cutover

Install Statistics first, then install Analysis Areas:

```bash
cd open-city-planner/backend
uv run python -m app.cli.modules verify analysis-areas-1.5.0.ocp
uv run python -m app.cli.modules install analysis-areas-1.5.0.ocp
uv run python -m app.cli.modules enable analysis-areas
```

Install defaults to disabled. Disable/re-enable preserves the installed wheel,
frontend package, tables and packaged migration history.

`scripts/host-contract-test` uses the normal Host CLI, installer, first-party and
entry-point discovery, generated `modules env`, frontend discovery, typecheck and
production build. Only the four duplicate Host Alembic files
are omitted from an isolated test copy for the exclusive-ownership graph check.

## Compatibility

The backend requires Module SDK `>=1.15.0,<2.0.0`. It receives the database,
module-scoped cache, cache generations, public-query policy, map preview,
polygon query/analytics capabilities through `ModuleContext` and resolves
`statistics.query@1` through the service registry. The installable Python package
has no private Host imports.
Analysis-Areas-specific schemas, filter parsing, cache keys and the spatial POI
query remain module-owned.
Wikidata is a module-owned external-provider adapter using only the production
SDK HTTP port; no direct `httpx` fallback exists in the installable package.
OSM area synchronization consumes the paginated
`platform.osm-snapshot-query@1` service and is triggered by
`osm.postprocessing-completed@1`. The same caller-owned transaction reconciles
`polygon_analysis_areas` through `platform.polygon-spatial-match@1` and
`platform.polygon-identity@1`; the module never reads `user_polygons`.

Existing Alembic IDs and their host-chain `down_revision` links are not renamed.
The module declares all four IDs explicitly through the SDK adoption contract;
future migrations must use `mod_analysis_areas_*` and extend the then-current
global head. No baseline table creation, graph rewrite, or data copy was introduced.
The lifecycle test removes duplicate built-in migration sources only in its
isolated cutover copy and validates passive discovery while installation is disabled.

Detailed evidence:

- [file parity](docs/file-parity.md)
- [test parity](docs/test-parity.md)
- [migration inventory](docs/migration-inventory.md)
- [import inventory](docs/import-inventory.md)
- [functional parity](docs/functional-parity.md)
- [OSM/Wikidata parity and blocking contracts](docs/sync-wikidata-parity.md)

## Host pin updates

`.github/ocp-host-contract.json` is the only pin source. Update it only to a
reviewed full commit SHA, rerun every standalone and host-contract gate, update
the extraction/parity notes if contracts changed, and commit the pin together
with those results. Never point CI at a branch name.

## Release

The release tag must equal `v` plus the version in `module.yaml`. Create and push
a release tag normally with:

```bash
git tag -a vX.Y.Z <commit> -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

If that tag already exists but its GitHub Release was not created, retry it via
**Actions → Release → Run workflow** and enter `vX.Y.Z` for `tag`. The manual
retry is only for an existing tag; it checks out and builds that exact tag rather
than the current `main` branch.

The release job reruns all gates, builds the `.ocp`, calculates SHA-256 and
refuses to mutate an existing release. Release note: “First standalone release
extracted from Open City Planner built-in module.”

## Cutover preconditions

The polygon UUID-to-internal-ID contract and assignment reconciliation are now
implemented and verified. Do not remove the built-in until release, registry,
lifecycle, migration, API, frontend and deployment/E2E gates are coordinated.
Never activate built-in and external `analysis-areas` simultaneously.

License: AGPL-3.0-only. OpenStreetMap-derived data remains subject to ODbL.
