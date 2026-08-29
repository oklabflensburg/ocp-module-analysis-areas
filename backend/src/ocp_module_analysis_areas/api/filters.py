"""Module-owned parsing for the established public polygon filters."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import HTTPException, Query

CATEGORIES = frozenset(
    {
        "warehouse",
        "fashion",
        "food",
        "electronics",
        "furniture",
        "garden",
        "other",
        "gastronomy",
        "services",
        "otherAreas",
        "__none__",
    }
)
FLOORS = frozenset({"UG", "EG", "OG"})
AREA_SIZES = frozenset({"S", "M", "L", "XL"})
OCCUPANCY_STATUSES = frozenset({"OCCUPIED", "VACANT", "UNKNOWN"})
BUSINESS_STRUCTURES = frozenset({"CHAIN", "INDEPENDENT", "UNKNOWN"})
DATA_SOURCES = frozenset({"STADTPLANNER", "OSM"})
NONE = "NONE"


def _values(raw: list[str] | None, allowed: frozenset[str], field: str) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(
            part.strip()
            for item in (raw or [])
            for part in item.split(",")
            if part.strip()
        )
    )
    if invalid := set(values) - (allowed | {NONE}):
        raise HTTPException(
            422,
            detail={
                "error": {
                    "code": "INVALID_POLYGON_FILTER",
                    "message": f"Ungültiger Wert für {field}.",
                    "values": sorted(invalid),
                }
            },
        )
    if NONE in values and len(values) > 1:
        raise HTTPException(
            422,
            detail={
                "error": {
                    "code": "INVALID_POLYGON_FILTER",
                    "message": f"NONE kann nicht mit einem Wert für {field} kombiniert werden.",
                    "values": sorted(values),
                }
            },
        )
    return values


@dataclass(frozen=True, slots=True)
class PolygonFilterParams:
    categories: tuple[str, ...] = ()
    floors: tuple[str, ...] = ()
    area_sizes: tuple[str, ...] = ()
    occupancy_statuses: tuple[str, ...] = ()
    business_structures: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


def polygon_filter_query(
    categories: Annotated[list[str] | None, Query()] = None,
    floors: Annotated[list[str] | None, Query()] = None,
    area_sizes: Annotated[list[str] | None, Query()] = None,
    occupancy_statuses: Annotated[list[str] | None, Query()] = None,
    business_structures: Annotated[list[str] | None, Query()] = None,
    sources: Annotated[list[str] | None, Query()] = None,
) -> PolygonFilterParams:
    return PolygonFilterParams(
        categories=_values(categories, CATEGORIES, "categories"),
        floors=_values(floors, FLOORS, "floors"),
        area_sizes=_values(area_sizes, AREA_SIZES, "area_sizes"),
        occupancy_statuses=_values(
            occupancy_statuses, OCCUPANCY_STATUSES, "occupancy_statuses"
        ),
        business_structures=_values(
            business_structures, BUSINESS_STRUCTURES, "business_structures"
        ),
        sources=_values(sources, DATA_SOURCES, "sources"),
    )
