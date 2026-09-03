"""Module-owned router preserving the production Analysis Areas API."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, NoReturn

from app.platform.modules.sdk import (
    CacheGenerationPort,
    CachePort,
    DatabaseSessionProvider,
    MapPreviewPort,
    MapPreviewRequest,
    MapPreviewUnavailableError,
    OsmSnapshotQueryPort,
    PolygonAnalyticsPort,
    PolygonQueryPort,
    PublicQueryPort,
    StatisticsQueryPort,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.cache import cache_status
from ..application.queries import (
    analysis_area_sitemap_entries,
    area_analytics,
    area_comparison,
    area_detail,
    area_detail_by_slug,
    area_polygons_by_slug,
    area_uuid_by_slug,
    areas_geojson,
    list_areas,
)
from ..settings import AnalysisAreasSettings
from .filters import PolygonFilterParams, polygon_filter_query
from .schemas import (
    AnalysisAreaAnalytics,
    AnalysisAreaComparison,
    AnalysisAreaDetail,
    AnalysisAreaPolygon,
    AnalysisAreaRead,
    AnalysisAreaSitemapEntry,
    AreaStatisticSeriesRead,
    AreaStatisticsRead,
)
from .statistics import (
    area_statistic_series_read,
    area_statistics_read,
    statistics_selection,
)

ANALYTICS_TIMEOUT_DETAIL = {
    "error": {
        "code": "ANALYTICS_QUERY_TIMEOUT",
        "message": "Die Gebietsanalyse konnte nicht rechtzeitig abgeschlossen werden.",
    }
}


def _filters(params: PolygonFilterParams) -> dict[str, tuple[str, ...]]:
    return {
        "categories": params.categories,
        "floors": params.floors,
        "area_sizes": params.area_sizes,
        "occupancy_statuses": params.occupancy_statuses,
        "business_structures": params.business_structures,
        "sources": params.sources,
    }


def create_router(
    database: DatabaseSessionProvider,
    cache: CachePort,
    cache_generations: CacheGenerationPort,
    public_queries: PublicQueryPort,
    map_previews: MapPreviewPort,
    polygons: PolygonQueryPort,
    polygon_analytics: PolygonAnalyticsPort,
    osm_snapshots: OsmSnapshotQueryPort,
    statistics: StatisticsQueryPort,
    settings: AnalysisAreasSettings,
) -> APIRouter:
    router = APIRouter(prefix="/analysis-areas", tags=["Analysis Areas"])
    maximum_items = public_queries.limits.max_response_items

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with database.session() as session:
            yield session

    SessionDep = Annotated[AsyncSession, Depends(session_dependency)]

    async def raise_analytics_database_error(
        session: AsyncSession, error: DBAPIError
    ) -> NoReturn:
        if not public_queries.is_timeout(error):
            raise error
        await session.rollback()
        raise HTTPException(status_code=503, detail=ANALYTICS_TIMEOUT_DETAIL) from error

    async def detail_by_slug(session: AsyncSession, slug: str) -> AnalysisAreaDetail | None:
        return await area_detail_by_slug(
            session, cache, cache_generations, settings, slug
        )

    @router.get("", response_model=list[AnalysisAreaRead], summary="Analysegebiete auflisten")
    async def get_areas(
        session: SessionDep,
        area_type: Annotated[str | None, Query()] = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[AnalysisAreaRead]:
        if area_type and area_type not in {"MUNICIPALITY", "DISTRICT", "QUARTER"}:
            raise HTTPException(422, "Ungültiger Gebietstyp.")
        return await list_areas(
            session, cache, cache_generations, settings, area_type, parent_id
        )

    @router.get("/geojson", summary="Analysegebiete als GeoJSON laden")
    async def get_areas_geojson(
        session: SessionDep,
        response: Response,
        limit: Annotated[int, Query(ge=1)] = maximum_items,
    ) -> dict:
        response.headers["Cache-Control"] = "public, max-age=300"
        result = await areas_geojson(
            session,
            cache,
            cache_generations,
            settings,
            limit=min(limit, maximum_items),
        )
        if public_queries.limits.cache_debug_headers and (status := cache_status()):
            response.headers["X-Cache"] = status
        return result

    @router.get(
        "/sitemap",
        response_model=list[AnalysisAreaSitemapEntry],
        summary="Indexierbare Gebietsseiten auflisten",
    )
    async def get_area_sitemap(session: SessionDep) -> list[AnalysisAreaSitemapEntry]:
        return await analysis_area_sitemap_entries(session)

    @router.get(
        "/by-slug/{slug}",
        response_model=AnalysisAreaDetail,
        summary="Öffentliches Gebiet per Slug laden",
    )
    async def get_area_by_slug(slug: str, session: SessionDep) -> AnalysisAreaDetail:
        result = await detail_by_slug(session, slug)
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return result

    @router.get("/by-slug/{slug}/preview.webp", response_class=Response)
    async def get_area_preview(
        slug: str,
        session: SessionDep,
        request: Request,
        width: Annotated[int, Query()] = 640,
        height: Annotated[int, Query()] = 360,
    ) -> Response:
        await public_queries.guard(request, session, "map-preview")
        area = await detail_by_slug(session, slug)
        if area is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        try:
            preview = await map_previews.render(
                MapPreviewRequest(
                    slug=area.slug,
                    updated_at=area.updated_at,
                    geometry=area.geometry.model_dump(),
                    bbox=area.bbox,
                    width=width,
                    height=height,
                    category=None,
                    feature_kind="area",
                )
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except MapPreviewUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc
        headers = {
            "ETag": preview.etag,
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
            "X-Content-Type-Options": "nosniff",
        }
        if request.headers.get("if-none-match") == preview.etag:
            return Response(status_code=304, headers=headers)
        return Response(preview.body, media_type=preview.content_type, headers=headers)

    @router.get(
        "/by-slug/{slug}/polygons",
        response_model=list[AnalysisAreaPolygon],
        summary="Verkaufsflächen eines Gebiets laden",
    )
    async def get_area_polygons_by_slug(
        slug: str,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=24)] = 8,
    ) -> list[AnalysisAreaPolygon]:
        result = await area_polygons_by_slug(
            session, cache, cache_generations, settings, polygons, slug, limit
        )
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return result

    @router.get(
        "/by-slug/{slug}/statistics",
        response_model=AreaStatisticsRead,
        summary="Kommunale Statistik eines Gebiets laden",
        description=(
            "Liefert lokal importierte Zahlenspiegel-Daten mit Quelle, Periode "
            "und Gebietsebene."
        ),
        tags=["Statistics"],
    )
    async def get_area_statistics(
        slug: str, session: SessionDep, request: Request
    ) -> AreaStatisticsRead:
        await public_queries.guard(request, session, "area-statistics")
        area = await detail_by_slug(session, slug)
        if area is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        result = await statistics.for_selection(session, statistics_selection(area))
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return area_statistics_read(result)

    @router.get(
        "/by-slug/{slug}/statistics/{metric_key}",
        response_model=AreaStatisticSeriesRead,
        summary="Zeitreihe einer kommunalen Gebietskennzahl laden",
        tags=["Statistics"],
    )
    async def get_area_statistic_series(
        slug: str, metric_key: str, session: SessionDep, request: Request
    ) -> AreaStatisticSeriesRead:
        await public_queries.guard(request, session, "area-statistic-series")
        area = await detail_by_slug(session, slug)
        if area is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        result = await statistics.series_for_selection(
            session, statistics_selection(area), metric_key
        )
        if result is None:
            raise HTTPException(404, "Die Gebietsstatistik wurde nicht gefunden.")
        return area_statistic_series_read(result)

    @router.get("/{area_id}", response_model=AnalysisAreaRead, summary="Analysegebiet per ID laden")
    async def get_area(area_id: uuid.UUID, session: SessionDep) -> AnalysisAreaRead:
        result = await area_detail(session, cache, cache_generations, settings, area_id)
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return result

    async def analytics_result(
        session: AsyncSession, area_id: uuid.UUID, params: PolygonFilterParams
    ) -> AnalysisAreaAnalytics | None:
        return await area_analytics(
            session,
            cache,
            cache_generations,
            settings,
            polygon_analytics,
            osm_snapshots,
            area_id,
            **_filters(params),
        )

    async def comparison_result(
        session: AsyncSession, area_id: uuid.UUID, params: PolygonFilterParams
    ) -> AnalysisAreaComparison | None:
        return await area_comparison(
            session,
            cache,
            cache_generations,
            settings,
            polygon_analytics,
            area_id,
            **_filters(params),
        )

    @router.get(
        "/by-slug/{slug}/analytics",
        response_model=AnalysisAreaAnalytics,
        summary="Aggregierte Gebietskennzahlen per Slug laden",
    )
    async def get_area_analytics_by_slug(
        slug: str, session: SessionDep, request: Request
    ) -> AnalysisAreaAnalytics:
        await public_queries.guard(request, session, "area-analytics")
        try:
            area_id = await area_uuid_by_slug(session, slug)
            if area_id is None:
                raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
            result = await analytics_result(session, area_id, PolygonFilterParams())
        except DBAPIError as exc:
            await raise_analytics_database_error(session, exc)
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return result

    @router.get(
        "/by-slug/{slug}/comparison",
        response_model=AnalysisAreaComparison,
        summary="Gebiet mit der Gesamtstadt vergleichen",
    )
    async def get_area_comparison_by_slug(
        slug: str, session: SessionDep, request: Request
    ) -> AnalysisAreaComparison:
        await public_queries.guard(request, session, "area-comparison")
        area_id = await area_uuid_by_slug(session, slug)
        if area_id is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        result = await comparison_result(session, area_id, PolygonFilterParams())
        if result is None:
            raise HTTPException(
                404, "Das Gebiet oder die zugehörige Gemeinde wurde nicht gefunden."
            )
        return result

    @router.get(
        "/{area_id}/analytics",
        response_model=AnalysisAreaAnalytics,
        summary="Gefilterte Gebietskennzahlen laden",
    )
    async def get_area_analytics(
        area_id: uuid.UUID,
        session: SessionDep,
        request: Request,
        filter_params: Annotated[PolygonFilterParams, Depends(polygon_filter_query)],
    ) -> AnalysisAreaAnalytics:
        await public_queries.guard(request, session, "area-analytics")
        try:
            result = await analytics_result(session, area_id, filter_params)
        except DBAPIError as exc:
            await raise_analytics_database_error(session, exc)
        if result is None:
            raise HTTPException(404, "Das Gebiet wurde nicht gefunden.")
        return result

    @router.get(
        "/{area_id}/comparison",
        response_model=AnalysisAreaComparison,
        summary="Gefilterten Gesamtstadtvergleich laden",
    )
    async def get_area_comparison(
        area_id: uuid.UUID,
        session: SessionDep,
        request: Request,
        filter_params: Annotated[PolygonFilterParams, Depends(polygon_filter_query)],
    ) -> AnalysisAreaComparison:
        await public_queries.guard(request, session, "area-comparison")
        result = await comparison_result(session, area_id, filter_params)
        if result is None:
            raise HTTPException(
                404, "Das Gebiet oder die zugehörige Gemeinde wurde nicht gefunden."
            )
        return result

    return router
