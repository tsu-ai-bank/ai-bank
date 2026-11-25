from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.passport import NonEmptyText, ProjectPassport


class PassportSource(BaseModel):
    """Input retained in both successful and failed generation results."""

    model_config = ConfigDict(frozen=True)

    document_id: int = Field(gt=0)
    faculty_id: int = Field(gt=0)
    text: NonEmptyText = Field(repr=False)
    competencies: list[NonEmptyText] = Field(min_length=1)


class GenerationError(BaseModel):
    code: Literal["invalid_response", "request_failed"]
    message: str
    retryable: bool
    status_code: int | None = None


class PassportGenerationResult(BaseModel):
    source: PassportSource
    status: Literal["GENERATED", "ERROR"]
    passport: ProjectPassport | None = None
    error: GenerationError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status == "GENERATED":
            if self.passport is None or self.error is not None:
                raise ValueError("Generated result requires a passport and no error")
        elif self.passport is not None or self.error is None:
            raise ValueError("Failed result requires an error and no passport")
        return self
