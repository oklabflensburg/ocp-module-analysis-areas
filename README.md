# Analysis Areas for Open City Planner

Standalone full-stack OCP module extracted from the built-in
`analysis-areas` module in
[`oklabflensburg/open-city-planner`](https://github.com/oklabflensburg/open-city-planner).

Version `1.1.0` is validated against host commit
`81844b666aca8356f9c5cb9a86f00cf15b784f79` on
`staging/epic-91-modular-host`. This repository is the future source of truth;
the built-in remains in the host checkout and is excluded at composition time.

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

The resulting files are `dist/analysis-areas-1.1.0.ocp` and its `.sha256`.
The `.ocp` is built by the pinned host's v1 builder, not by repository-local ZIP
code.

## Wikidata operations

The Wikidata implementation is ready and the backend publishes the versioned
service contract `analysis-areas.wikidata-maintenance` (version 1), whose
`sync(force=...)` and `set_manual_match(area, qid,
allow_name_mismatch=...)` methods preserve the old refresh and manual-assignment
capabilities. Reads, provider calls and writes use separate phases, so Wikidata
latency never retains a checked-out DB session.

Automatic execution is intentionally disabled: SDK 1.9's public
`CacheGenerationPort` can only read `current(...)`, while the historical workflow
atomically bumped the shared `analysis-areas` generation in the same transaction
as its database writes. Consequently `analysis-areas.wikidata-refresh` is not
registered until the Host supplies a transactional public generation-bump
operation. This prevents scheduled writes from leaving generation-keyed consumers
stale.

The pinned Host has no generic CLI for passing arguments to module maintenance
commands (or for running a future safely registered job). Therefore the old three
Host-specific CLI entry points cannot yet be replaced by a documented operator
command. This and the OSM postprocessing/event dependencies are precise blocking
contracts, not removed functionality; see the parity inventory before any Host
cleanup.

## Installation and cutover

Select the external owner through the shared host composition setting:

```bash
cd open-city-planner/backend
export OCP_EXCLUDED_BUILTIN_MODULES=analysis-areas
uv run python -m app.cli.modules verify analysis-areas-1.1.0.ocp
uv run python -m app.cli.modules install analysis-areas-1.1.0.ocp
uv run python -m app.cli.modules enable analysis-areas
```

Install defaults to disabled. Disable/re-enable preserves the installed wheel,
frontend package, tables and packaged migration history.

`scripts/host-contract-test` uses the normal Host CLI, installer, first-party and
entry-point discovery, generated `modules env`, frontend discovery, typecheck and
production build. The Built-in backend and frontend stay on disk and are excluded
only by `OCP_EXCLUDED_BUILTIN_MODULES`. Only the four duplicate Host Alembic files
are omitted from an isolated test copy for the exclusive-ownership graph check.

## Compatibility

The backend requires Module SDK `>=1.9.0,<2.0.0`. It receives the database,
module-scoped cache, cache generations, public-query policy, map preview,
polygon query/analytics and statistics capabilities exclusively through its
`ModuleContext`. The installable Python package has no private Host imports.
Analysis-Areas-specific schemas, filter parsing, cache keys and the spatial POI
query remain module-owned.
Wikidata is a module-owned external-provider adapter. It prefers the SDK HTTP
port. The pinned production context leaves that optional port unwired, so this
trusted in-process module temporarily uses its declared `httpx` dependency with
explicit timeout, User-Agent, bounded retry and context-managed cleanup. The Host
architecture assigns safe HTTP-client infrastructure to the Host; wiring the
existing public port remains a Host follow-up so this fallback need not be permanent.

Existing Alembic IDs and their host-chain `down_revision` links are not renamed.
The module declares all four IDs explicitly through the SDK 1.9 adoption contract;
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

Do not remove the built-in until the blocking OSM/event/cache/operations contracts
in the parity inventory are available and the resulting sync is verified, in
addition to release, registry, lifecycle, migration, API, frontend and E2E gates.
Never activate built-in and external `analysis-areas` simultaneously.

License: AGPL-3.0-only. OpenStreetMap-derived data remains subject to ODbL.
