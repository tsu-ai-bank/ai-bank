from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PassportSection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Sprint(PassportSection):
    number: int = Field(ge=1, le=4)
    goal: NonEmptyText
    tasks: list[NonEmptyText] = Field(min_length=1)


class TeamRole(PassportSection):
    name: NonEmptyText
    responsibilities: list[NonEmptyText] = Field(min_length=1)


class EffortEstimate(PassportSection):
    total_hours: int = Field(gt=0)
    explanation: NonEmptyText


class CourseRoute(PassportSection):
    course: int = Field(ge=1, le=4)
    rationale: NonEmptyText


class TechnologyStack(PassportSection):
    no_code: list[NonEmptyText] = Field(min_length=1)
    web: list[NonEmptyText] = Field(min_length=1)


class ProjectPassport(PassportSection):
    backlog: list[Sprint] = Field(min_length=4, max_length=4)
    roles: list[TeamRole] = Field(min_length=1)
    effort: EffortEstimate
    course_routing: list[CourseRoute] = Field(min_length=1)
    stack: TechnologyStack
    business_value: NonEmptyText
    custdev_guide: list[NonEmptyText] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sprint_numbers(self) -> Self:
        if {sprint.number for sprint in self.backlog} != {1, 2, 3, 4}:
            raise ValueError("Backlog must contain sprints 1, 2, 3 and 4 exactly once")
        return self
