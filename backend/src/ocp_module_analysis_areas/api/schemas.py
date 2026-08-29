"""Stable public API schemas owned by the Analysis Areas module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Position = tuple[float, float]


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[Position]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, rings: list[list[Position]]) -> list[list[Position]]:
        if not rings:
            raise ValueError("Polygon requires at least one linear ring")
        for ring in rings:
            if len(ring) < 4:
                raise ValueError("Linear rings need at least four positions")
            if ring[0] != ring[-1]:
                raise ValueError("Lineare Ringe müssen geschlossen sein")
            for longitude, latitude in ring:
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError(
                        "Coordinates must use EPSG:4326 longitude/latitude ranges"
                    )
        if sum(len(ring) for ring in rings) > 5_000:
            raise ValueError("Polygon exceeds maximum vertex count")
        return rings


class MultiPolygonGeometry(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Position]]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(
        cls, polygons: list[list[list[Position]]]
    ) -> list[list[list[Position]]]:
        if not polygons:
            raise ValueError("MultiPolygon requires at least one polygon")
        for rings in polygons:
            PolygonGeometry(type="Polygon", coordinates=rings)
        if sum(len(ring) for polygon in polygons for ring in polygon) > 10_000:
            raise ValueError("MultiPolygon exceeds maximum vertex count")
        return polygons


AreaGeometry = PolygonGeometry | MultiPolygonGeometry


class WikidataExternalLink(BaseModel):
    id: str
    url: str


class WikipediaExternalLink(BaseModel):
    title: str
    url: str


class AnalysisAreaExternalLinks(BaseModel):
    wikidata: WikidataExternalLink | None = None
    wikipedia: WikipediaExternalLink | None = None

class AnalysisAreaRead(BaseModel):
    id: str
    slug: str
    name: str
    area_type: str
    parent_id: str | None = None
    parent_name: str | None = None
    parent_slug: str | None = None
    area_m2: float
    source: str
    source_osm_type: str | None = None
    source_osm_id: int | None = None
    source_admin_level: int | None = None
    source_place: str | None = None
    source_updated_at: datetime | None = None
    updated_at: datetime
    child_count: int = 0
    external_links: AnalysisAreaExternalLinks = Field(default_factory=AnalysisAreaExternalLinks)


class AnalysisAreaReference(BaseModel):
    id: str
    slug: str
    name: str
    area_type: str


class AnalysisAreaDetail(AnalysisAreaRead):
    parent: AnalysisAreaReference | None = None
    municipality: AnalysisAreaReference | None = None
    children: list[AnalysisAreaReference] = Field(default_factory=list)
    geometry: AreaGeometry
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]


class AnalysisAreaPolygon(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    floor: str | None = None
    address_display_name: str | None = None
    occupancy_status: str
    area_m2: float | None = None


class AnalysisAreaSitemapEntry(BaseModel):
    slug: str
    updated_at: datetime


class DimensionCount(BaseModel):
    key: str
    label: str
    count: int


class CompletenessMetric(BaseModel):
    key: str
    label: str
    complete: int
    total: int
    percent: float | None = None


class BenchmarkMetrics(BaseModel):
    polygon_count: int
    occupied_count: int
    vacant_count: int
    chain_count: int
    independent_count: int
    total_area_m2: float | None = None
    average_area_m2: float | None = None
    median_area_m2: float | None = None
    vacant_area_m2: float | None = None
    vacancy_area_rate: float | None = None
    vacancy_rate: float | None = None
    chain_store_rate: float | None = None
    known_occupancy_count: int
    known_business_structure_count: int
    data_updated_at: datetime | None = None
    size_distribution: list[DimensionCount] = Field(default_factory=list)
    floor_distribution: list[DimensionCount] = Field(default_factory=list)
    status_distribution: list[DimensionCount] = Field(default_factory=list)
    business_structure_distribution: list[DimensionCount] = Field(default_factory=list)
    data_completeness: list[CompletenessMetric] = Field(default_factory=list)


class IndustryCount(BaseModel):
    category: str
    count: int


class AnalysisAreaAnalytics(BaseModel):
    area: AnalysisAreaRead
    metrics: BenchmarkMetrics
    industry_distribution: list[IndustryCount]
    poi_count: int
    poi_categories: list[IndustryCount]
    retail_area_density_m2_per_km2: float | None = None


class MetricDifference(BaseModel):
    key: str
    area_value: float | int | None
    municipality_value: float | int | None
    difference: float | None
    unit: str = "absolute"


class AnalysisAreaComparison(BaseModel):
    area: AnalysisAreaRead
    municipality: AnalysisAreaRead
    area_metrics: BenchmarkMetrics
    municipality_metrics: BenchmarkMetrics
    differences: list[MetricDifference] = Field(default_factory=list)


class StatisticsAreaReference(BaseModel):
    id: str
    slug: str
    name: str
    area_type: str


class StatisticsSource(BaseModel):
    name: str
    url: str
    license: str
    source_updated_at: datetime | None
    last_import_at: datetime | None


class AreaStatisticValue(BaseModel):
    key: str
    name: str
    category: str
    value: Decimal | None
    unit: str
    period: str
    period_start: date
    area_level: str
    is_calculated: bool
    municipality_value: Decimal | None = None
    difference: Decimal | None = None
    relative_difference: Decimal | None = None


class AreaStatisticsRead(BaseModel):
    area: StatisticsAreaReference
    statistics_area: StatisticsAreaReference
    inherited_from_parent: bool
    source: StatisticsSource | None
    latest: list[AreaStatisticValue] = Field(default_factory=list)


class StatisticSeriesPoint(BaseModel):
    period: str
    period_start: date
    value: Decimal | None
    suppressed: bool


class AreaStatisticSeriesRead(BaseModel):
    area: StatisticsAreaReference
    statistics_area: StatisticsAreaReference
    inherited_from_parent: bool
    source: StatisticsSource | None
    metric: dict[str, str]
    series: list[StatisticSeriesPoint] = Field(default_factory=list)
