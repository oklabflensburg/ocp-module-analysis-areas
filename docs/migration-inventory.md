# Migration inventory

Source: `open-city-planner@81844b666aca8356f9c5cb9a86f00cf15b784f79`.
The files under `ocp_module_analysis_areas/migrations/history` are immutable
copies; no revision ID, `down_revision`, table, column, constraint, index, SRID,
or backfill was rewritten.

| Revision | Down revision | Ownership and operations |
| --- | --- | --- |
| `20260814_0014` | `20260814_0013` | Creates `analysis_areas` and `polygon_analysis_areas`; UUID and slug uniqueness; self-parent FK `SET NULL`; polygon/user and polygon/area FKs `CASCADE`; `MULTIPOLYGON(4326)` geometry, `POINT(4326)` centroid; type/source checks; OSM identity uniqueness; parent/type/GiST and association indexes. |
| `20260817_0023` | `20260817_0022` | Adds OSM/Wikidata/Wikipedia provenance and match columns, three checks, `wikidata_verified`; backfills OSM tags from `osm_features`. |
| `20260818_0025` | `20260818_0024` | Widens `source_osm_wikidata`, extends match status with `INVALID`, and adds `idx_analysis_areas_wikidata_id`; downgrade restores the prior contract. |
| `20260819_0032` | `20260819_0031` | Historical OSM POI index. Runtime POI reads now use the public snapshot port; this adopted revision remains byte-identical because published migration history cannot be rewritten. |

The Statistics revision `20260816_0016` creates `statistics_*` tables with FKs
to `analysis_areas`. It remains intentionally host/Statistics-owned and is listed
in the parity report rather than relabeled as Analysis Areas persistence.

## Adoption contract

The standalone module declares these exact IDs in
`ModuleMigrationSource.adopted_revisions` and exposes `migrations/history` from
the installed `ocp_module_analysis_areas` package. Its manifest consequently sets
`persistence.migrations: true`. This transfers source ownership without renaming
revisions, rewriting graph edges, introducing a baseline, or changing the single
global Alembic version table.

All future revisions use the `mod_analysis_areas_` namespace. A future revision
such as `mod_analysis_areas_0001` must extend the global Alembic head that exists
when it is authored; it must not automatically point to `20260819_0032` merely
because that is the last adopted Analysis Areas revision.

The pinned host still retains its built-in migration copies. Providing both copies
to one coordinator is intentionally a fail-fast duplicate-revision error. The
contract test removes only those four files from an isolated Alembic test copy to
prove the final exclusive-ownership graph; no host checkout file is changed.
