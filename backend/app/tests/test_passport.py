from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from src.schemas.passport import ProjectPassport
from src.schemas.passport_generation import PassportGenerationResult, PassportSource


def test_passport_has_seven_sections(passport_payload: dict[str, Any]) -> None:
    passport = ProjectPassport.model_validate(passport_payload)
    assert set(passport.model_dump()) == {
        "backlog",
        "roles",
        "effort",
        "course_routing",
        "stack",
        "business_value",
        "custdev_guide",
    }
    assert ProjectPassport.model_validate_json(passport.model_dump_json()) == passport


@pytest.mark.parametrize(
    "section",
    [
        "backlog",
        "roles",
        "effort",
        "course_routing",
        "stack",
        "business_value",
        "custdev_guide",
    ],
)
def test_every_section_is_required(
    passport_payload: dict[str, Any], section: str
) -> None:
    passport_payload.pop(section)
    with pytest.raises(ValidationError):
        ProjectPassport.model_validate(passport_payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("roles",), []),
        (("business_value",), "   "),
        (("custdev_guide",), []),
        (("effort", "total_hours"), 0),
        (("effort", "total_hours"), True),
        (("course_routing", 0, "course"), 5),
        (("backlog", 0, "number"), 2),
        (("backlog", 0, "tasks"), []),
        (("stack", "web"), []),
        (("stack", "unknown"), "unexpected"),
    ],
)
def test_invalid_nested_content_is_rejected(
    passport_payload: dict[str, Any], path: tuple, value: Any
) -> None:
    payload = deepcopy(passport_payload)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        ProjectPassport.model_validate(payload)


@pytest.mark.parametrize("status", ["GENERATED", "ERROR"])
def test_result_cannot_have_an_incomplete_outcome(
    passport_source: PassportSource, status: str
) -> None:
    with pytest.raises(ValidationError):
        PassportGenerationResult(source=passport_source, status=status)
