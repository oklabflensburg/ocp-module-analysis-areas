import uuid

from app.platform.modules.sdk import CacheGenerationPort, CachePort, DatabaseSessionProvider

from ..contracts import AnalysisAreaGeometry, AnalysisAreaSummary
from ..settings import AnalysisAreasSettings
from .queries import area_detail, area_detail_by_slug, list_areas


def _summary(area) -> AnalysisAreaSummary:
    return AnalysisAreaSummary(
        id=area.id,
        slug=area.slug,
        name=area.name,
        area_type=area.area_type,
        parent_id=area.parent_id,
    )


class SqlAnalysisAreaQueryService:
    """Materializing public query service; no ORM/session type escapes the module."""

    def __init__(
        self,
        database: DatabaseSessionProvider,
        cache: CachePort,
        cache_generations: CacheGenerationPort,
        settings: AnalysisAreasSettings,
    ) -> None:
        self._database = database
        self._cache = cache
        self._cache_generations = cache_generations
        self._settings = settings

    async def list_areas(
        self, *, area_type: str | None = None, parent_id: str | None = None
    ) -> tuple[AnalysisAreaSummary, ...]:
        parent_uuid = uuid.UUID(parent_id) if parent_id else None
        async with self._database.session() as session:
            values = await list_areas(
                session,
                self._cache,
                self._cache_generations,
                self._settings,
                area_type,
                parent_uuid,
            )
            return tuple(_summary(area) for area in values)

    async def get_by_id(self, area_id: str) -> AnalysisAreaSummary | None:
        async with self._database.session() as session:
            area = await area_detail(
                session,
                self._cache,
                self._cache_generations,
                self._settings,
                uuid.UUID(area_id),
            )
        return _summary(area) if area else None

    async def get_by_slug(self, slug: str) -> AnalysisAreaSummary | None:
        async with self._database.session() as session:
            area = await area_detail_by_slug(
                session, self._cache, self._cache_generations, self._settings, slug
            )
        return _summary(area) if area else None

    async def get_geometry(self, slug: str) -> AnalysisAreaGeometry | None:
        async with self._database.session() as session:
            area = await area_detail_by_slug(
                session, self._cache, self._cache_generations, self._settings, slug
            )
        if area is None:
            return None
        return AnalysisAreaGeometry(
            id=area.id,
            slug=area.slug,
            geometry=area.geometry.model_dump(),
        )

    async def get_parent(self, slug: str) -> AnalysisAreaSummary | None:
        async with self._database.session() as session:
            area = await area_detail_by_slug(
                session, self._cache, self._cache_generations, self._settings, slug
            )
        if area is None or area.parent is None:
            return None
        return AnalysisAreaSummary(
            id=area.parent.id,
            slug=area.parent.slug,
            name=area.parent.name,
            area_type=area.parent.area_type,
            parent_id=None,
        )

    async def list_children(self, slug: str) -> tuple[AnalysisAreaSummary, ...]:
        async with self._database.session() as session:
            area = await area_detail_by_slug(
                session, self._cache, self._cache_generations, self._settings, slug
            )
        if area is None:
            return ()
        return tuple(
            AnalysisAreaSummary(
                id=child.id,
                slug=child.slug,
                name=child.name,
                area_type=child.area_type,
                parent_id=area.id,
            )
            for child in area.children
        )
