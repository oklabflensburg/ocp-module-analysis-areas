"""Validated settings owned by the Analysis Areas module."""

from pydantic import BaseModel, ConfigDict, Field


class AnalysisAreasSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_area_cache_ttl: int = Field(default=3_600, ge=1)
    analytics_cache_ttl: int = Field(default=600, ge=1)
