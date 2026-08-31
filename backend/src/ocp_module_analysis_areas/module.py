"""Composition root for the production Analysis Areas module."""

from app.platform.modules.sdk import (
    JobDefinition,
    ModuleContext,
    ModuleDefinition,
    ModuleMigrationSource,
    ModulePersistenceContribution,
    ModuleSettingsContribution,
    parse_manifest,
)

from .api.router import create_router
from .application import SqlAnalysisAreaQueryService, WikidataEnrichmentService
from .contracts import (
    MAINTENANCE_SERVICE_ID,
    MAINTENANCE_SERVICE_VERSION,
    SERVICE_ID,
    SERVICE_VERSION,
    AnalysisAreaQueryService,
    WikidataMaintenanceService,
)
from .integrations.wikidata import WikidataClient
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
            "analysis-areas.wikidata-maintenance",
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
            "scheduler": context.scheduler,
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
        assert context.scheduler is not None
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
        wikidata = WikidataEnrichmentService(
            context.database,
            context.cache,
            WikidataClient(
                context.http,
                context.cache,
                api_url=settings.wikidata_api_url,
                cache_ttl_seconds=settings.wikidata_cache_ttl_seconds,
                negative_cache_ttl_seconds=settings.wikidata_negative_cache_ttl_seconds,
                search_limit=settings.wikidata_search_limit,
                timeout_seconds=settings.wikidata_timeout_seconds,
                user_agent=settings.wikidata_user_agent,
            ),
            stale_days=settings.wikidata_stale_days,
        )
        context.services.register(
            WikidataMaintenanceService,
            wikidata,
            service_id=MAINTENANCE_SERVICE_ID,
            version=MAINTENANCE_SERVICE_VERSION,
        )

        async def refresh_wikidata(_context: ModuleContext) -> object:
            report = await wikidata.sync()
            context.observability.metrics.observe("wikidata-checked", float(report.checked))
            context.observability.metrics.observe(
                "wikidata-errors", float(len(report.errors))
            )
            context.logger.info(
                "Wikidata enrichment completed",
                extra={
                    "checked": report.checked,
                    "matched": report.osm_wikidata
                    + report.osm_wikipedia
                    + report.search,
                    "errors": len(report.errors),
                },
            )
            return report

        context.scheduler.register(
            JobDefinition(job_id="wikidata-refresh", handler=refresh_wikidata)
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
