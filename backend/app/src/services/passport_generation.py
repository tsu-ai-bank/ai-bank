from pydantic import ValidationError

from src.core.prompts import PASSPORT_SYSTEM_PROMPT, build_passport_user_prompt
from src.schemas.passport import ProjectPassport
from src.schemas.passport_generation import (
    GenerationError,
    PassportGenerationResult,
    PassportSource,
)
from src.services.deepseek import (
    DeepSeekClient,
    DeepSeekRequestError,
    DeepSeekResponseError,
)


class PassportGenerator:
    def __init__(self, client: DeepSeekClient) -> None:
        self._client = client

    async def generate(self, source: PassportSource) -> PassportGenerationResult:
        try:
            content = await self._client.complete_json(
                system_prompt=PASSPORT_SYSTEM_PROMPT,
                user_prompt=build_passport_user_prompt(source),
            )
            passport = ProjectPassport.model_validate_json(content)
        except (ValidationError, DeepSeekResponseError):
            error = GenerationError(
                code="invalid_response",
                message="DeepSeek response does not match the passport schema",
                retryable=True,
            )
        except DeepSeekRequestError as exc:
            error = GenerationError(
                code="request_failed",
                message=str(exc),
                retryable=exc.retryable,
                status_code=exc.status_code,
            )
        else:
            return PassportGenerationResult(
                source=source, status="GENERATED", passport=passport
            )
        return PassportGenerationResult(source=source, status="ERROR", error=error)
