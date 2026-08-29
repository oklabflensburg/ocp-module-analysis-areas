"""Composition root for the production Analysis Areas module."""

from app.platform.modules.sdk import (
    ModuleContext,
    ModuleDefinition,
    ModuleMigrationSource,
    ModulePersistenceContribution,
    parse_manifest,
)

from .api import router
from .application import SqlAnalysisAreaQueryService
from .contracts import SERVICE_ID, SERVICE_VERSION, AnalysisAreaQueryService
from .persistence import METADATA

MANIFEST = parse_manifest(
    {
        "manifest_version": 1,
        "id": "analysis-areas",
        "name": "Analysis Areas",
        "version": "1.0.0",
        "requires": {"host": ">=0.2.0,<1.0.0", "sdk": ">=1.8.0,<2.0.0"},
        "backend": {"package": "ocp-module-analysis-areas"},
        "frontend": {"package": "@open-city-planner/analysis-areas"},
        "capabilities": [
            "analysis-areas.public-api",
            "analysis-areas.lookup",
            "analysis-areas.geojson",
        ],
        "persistence": {"schema": "analysis_areas", "migrations": True},
    },
    origin=__name__,
)


class AnalysisAreasModule:
    manifest = MANIFEST

    def register(self, context: ModuleContext) -> None:
        if context.database is None:
            raise RuntimeError("The Analysis Areas module requires the database port.")
        if context.services is None:
            raise RuntimeError("The Analysis Areas module requires the service registry.")
        context.api.include_router(router, prefix="/api/v1", tags=("Analysis Areas",))
        context.services.register(
            AnalysisAreaQueryService,
            SqlAnalysisAreaQueryService(context.database),
            service_id=SERVICE_ID,
            version=SERVICE_VERSION,
        )


DEFINITION = ModuleDefinition(
    manifest=MANIFEST,
    loader=AnalysisAreasModule,
    origin=__name__,
    declared_id=MANIFEST.id,
    persistence=ModulePersistenceContribution(
        module_id=MANIFEST.id,
        metadata=METADATA,
        schema="analysis_areas",
        migration_source=ModuleMigrationSource(
            package="ocp_module_analysis_areas",
            resource="migrations/history",
            revision_namespace="mod_analysis_areas",
            adopted_revisions=frozenset(
                {
                    "20260814_0014",
                    "20260817_0023",
                    "20260818_0025",
                    "20260819_0032",
                }
            ),
        ),
        adopted_tables=frozenset({"analysis_areas"}),
    ),
)
