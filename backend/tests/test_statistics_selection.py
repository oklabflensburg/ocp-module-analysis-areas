import uuid

from ocp_module_analysis_areas.api.schemas import AnalysisAreaDetail, AnalysisAreaReference
from ocp_module_analysis_areas.api.statistics import statistics_selection

MUNICIPALITY_ID = "11111111-1111-4111-8111-111111111111"
DISTRICT_ID = "22222222-2222-4222-8222-222222222222"
QUARTER_ID = "33333333-3333-4333-8333-333333333333"


def reference(identifier: str, slug: str, name: str, area_type: str) -> AnalysisAreaReference:
    return AnalysisAreaReference(
        id=identifier,
        slug=slug,
        name=name,
        area_type=area_type,
    )


def detail(
    identifier: str,
    slug: str,
    name: str,
    area_type: str,
    *,
    parent: AnalysisAreaReference | None = None,
    municipality: AnalysisAreaReference | None = None,
) -> AnalysisAreaDetail:
    return AnalysisAreaDetail.model_construct(
        id=identifier,
        slug=slug,
        name=name,
        area_type=area_type,
        parent=parent,
        municipality=municipality,
    )


def test_municipality_selects_itself_for_statistics_and_comparison() -> None:
    area = detail(MUNICIPALITY_ID, "flensburg", "Flensburg", "MUNICIPALITY")

    selection = statistics_selection(area)

    assert selection.requested.id == uuid.UUID(MUNICIPALITY_ID)
    assert selection.target == selection.requested
    assert selection.municipality == selection.requested
    assert selection.inherited is False


def test_district_selects_itself_and_its_municipality() -> None:
    municipality = reference(
        MUNICIPALITY_ID, "flensburg", "Flensburg", "MUNICIPALITY"
    )
    area = detail(
        DISTRICT_ID,
        "altstadt-15630273",
        "Altstadt",
        "DISTRICT",
        parent=municipality,
        municipality=municipality,
    )

    selection = statistics_selection(area)

    assert selection.target.id == uuid.UUID(DISTRICT_ID)
    assert selection.municipality.id == uuid.UUID(MUNICIPALITY_ID)
    assert selection.inherited is False


def test_quarter_selects_parent_district_and_preserves_requested_area() -> None:
    municipality = reference(
        MUNICIPALITY_ID, "flensburg", "Flensburg", "MUNICIPALITY"
    )
    district = reference(
        DISTRICT_ID, "altstadt-15630273", "Altstadt", "DISTRICT"
    )
    area = detail(
        QUARTER_ID,
        "nordertor-123",
        "Nordertor",
        "QUARTER",
        parent=district,
        municipality=municipality,
    )

    selection = statistics_selection(area)

    assert selection.requested.id == uuid.UUID(QUARTER_ID)
    assert selection.target.id == uuid.UUID(DISTRICT_ID)
    assert selection.municipality.id == uuid.UUID(MUNICIPALITY_ID)
    assert selection.inherited is True
