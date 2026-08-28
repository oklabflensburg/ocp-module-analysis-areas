# Migration inventory

Source: `open-city-planner@b8c4db7f3246d21c53a1b5633915be16bb84a633`.
The files under `ocp_module_analysis_areas/migrations/history` are immutable
copies; no revision ID, `down_revision`, table, column, constraint, index, SRID,
or backfill was rewritten.

| Revision | Down revision | Ownership and operations |
| --- | --- | --- |
| `20260814_0014` | `20260814_0013` | Creates `analysis_areas` and `polygon_analysis_areas`; UUID and slug uniqueness; self-parent FK `SET NULL`; polygon/user and polygon/area FKs `CASCADE`; `MULTIPOLYGON(4326)` geometry, `POINT(4326)` centroid; type/source checks; OSM identity uniqueness; parent/type/GiST and association indexes. |
| `20260817_0023` | `20260817_0022` | Adds OSM/Wikidata/Wikipedia provenance and match columns, three checks, `wikidata_verified`; backfills OSM tags from `osm_features`. |
| `20260818_0025` | `20260818_0024` | Widens `source_osm_wikidata`, extends match status with `INVALID`, and adds `idx_analysis_areas_wikidata_id`; downgrade restores the prior contract. |
| `20260819_0032` | `20260819_0031` | Adds the concurrent partial GiST index `idx_osm_features_poi_geometry` for the area POI query. The physical table belongs to OSM, but the revision is retained because it is part of the characterized area-POI performance contract. |

The Statistics revision `20260816_0016` creates `statistics_*` tables with FKs
to `analysis_areas`. It remains intentionally host/Statistics-owned and is listed
in the parity report rather than relabeled as Analysis Areas persistence.

## Runtime status

The current host module migration coordinator requires new external revisions to
use the `mod_analysis_areas_` namespace and to form one global linear chain.
Renaming these released host revisions would break existing databases, while
registering a new create-all baseline would duplicate production tables. The
standalone manifest therefore retains the existing adoption contract
(`schema: analysis_areas`, `migrations: false`) and packages the immutable history
as audit/upgrade resources. The host continues to own execution of these existing
chain nodes until a follow-up contract supports adopted historical revisions.

This is a known cutover prerequisite, not a new schema or a hidden migration.
