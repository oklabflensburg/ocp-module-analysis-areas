"""Validated settings owned by the Analysis Areas module."""

from pydantic import BaseModel, ConfigDict, Field


class AnalysisAreasSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_area_cache_ttl: int = Field(default=3_600, ge=1)
    analytics_cache_ttl: int = Field(default=600, ge=1)
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    wikidata_user_agent: str = (
        "Stadtplaner/1.0 (https://stadtplaner.oklabflensburg.de; OK Lab Flensburg)"
    )
    wikidata_timeout_seconds: float = Field(default=10.0, gt=0)
    wikidata_cache_ttl_seconds: int = Field(default=604_800, ge=1)
    wikidata_negative_cache_ttl_seconds: int = Field(default=86_400, ge=1)
    wikidata_stale_days: int = Field(default=90, ge=1)
    wikidata_search_limit: int = Field(default=8, ge=1, le=50)
