"""Composition root for the production Analysis Areas module."""

from app.platform.modules.sdk import (
    ModuleContext,
    ModuleDefinition,
    ModuleMigrationSource,
    ModulePersistenceContribution,
    ModuleSettingsContribution,
    parse_manifest,
)

from .api.router import create_router
from .application import SqlAnalysisAreaQueryService
from .contracts import (
    SERVICE_ID,
    SERVICE_VERSION,
    AnalysisAreaQueryService,
)
from .persistence import METADATA
from .settings import AnalysisAreasSettings

MANIFEST = parse_manifest(
    {
        "manifest_version": 1,
        "id": "analysis-areas",
        "name": "Analysis Areas",
        "version": "1.1.0",
        "requires": {"host": ">=0.2.0,<1.0.0", "sdk": ">=1.9.0,<2.0.0"},
        "backend": {"package": "ocp-module-analysis-areas"},
        "frontend": {"package": "@open-city-planner/analysis-areas"},
        "capabilities": [
            "analysis-areas.public-api",
            "analysis-areas.lookup",
            "analysis-areas.geojson",
        ],
        "config": {"namespace": "analysis-areas"},
        "persistence": {"schema": "analysis_areas", "migrations": True},
    },
    origin=__name__,
)


class AnalysisAreasModule:
    manifest = MANIFEST

    def register(self, context: ModuleContext) -> None:
        required = {
            "database": context.database,
            "cache": context.cache,
            "cache generations": context.cache_generations,
            "public queries": context.public_queries,
            "map previews": context.map_previews,
            "polygon queries": context.polygons,
            "polygon analytics": context.polygon_analytics,
            "statistics": context.statistics,
            "settings": context.settings,
        }
        if missing := [name for name, port in required.items() if port is None]:
            raise RuntimeError(
                "The Analysis Areas module requires these public ports: "
                + ", ".join(missing)
            )
        if context.services is None:
            raise RuntimeError("The Analysis Areas module requires the service registry.")
        assert context.database is not None
        assert context.cache is not None
        assert context.cache_generations is not None
        assert context.public_queries is not None
        assert context.map_previews is not None
        assert context.polygons is not None
        assert context.polygon_analytics is not None
        assert context.statistics is not None
        assert context.settings is not None
        settings = context.settings.require(AnalysisAreasSettings)
        router = create_router(
            context.database,
            context.cache,
            context.cache_generations,
            context.public_queries,
            context.map_previews,
            context.polygons,
            context.polygon_analytics,
            context.statistics,
            settings,
        )
        context.api.include_router(router, prefix="/api/v1", tags=("Analysis Areas",))
        context.services.register(
            AnalysisAreaQueryService,
            SqlAnalysisAreaQueryService(
                context.database, context.cache, context.cache_generations, settings
            ),
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
    settings=ModuleSettingsContribution(
        module_id=MANIFEST.id,
        namespace="analysis-areas",
        model=AnalysisAreasSettings,
    ),
)
