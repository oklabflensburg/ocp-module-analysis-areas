from sqlalchemy import MetaData

from .models import AnalysisArea, PolygonAnalysisArea

METADATA = MetaData()
AnalysisArea.__table__.to_metadata(METADATA)
PolygonAnalysisArea.__table__.to_metadata(METADATA)

__all__ = ["METADATA", "AnalysisArea", "PolygonAnalysisArea"]
