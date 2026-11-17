import json
from typing import Any

import httpx
import pytest

from src.core.config import Settings
from src.schemas.passport_generation import PassportGenerationResult, PassportSource
from src.services.deepseek import DeepSeekClient
from src.services.passport_generation import PassportGenerator
from tests.fakes import FakeClock, completion_response

pytestmark = pytest.mark.anyio


async def test_generation_uses_provided_competencies_and_preserves_source(
    deepseek_settings: Settings,
    passport_source: PassportSource,
    passport_payload: dict[str, Any],
) -> None:
    before = passport_source.model_dump()

    def handler(request: httpx.Request) -> httpx.Response:
        messages = json.loads(request.content)["messages"]
        assert "JSON" in messages[0]["content"]
        assert "backlog" in messages[0]["content"]
        data = json.loads(messages[1]["content"])
        assert data["faculty_competencies"] == passport_source.competencies
        assert data["document_text"] == passport_source.text
        assert data["faculty_id"] == passport_source.faculty_id
        return completion_response(json.dumps(passport_payload))

    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(handler)
    ) as client:
        result = await PassportGenerator(client).generate(passport_source)
    assert result.status == "GENERATED"
    assert result.passport is not None
    assert result.error is None
    assert result.source is passport_source
    assert passport_source.model_dump() == before
    assert (
        PassportGenerationResult.model_validate_json(result.model_dump_json()) == result
    )


@pytest.mark.parametrize("content", ["not JSON", "{}", '{"backlog": []}', "   "])
async def test_invalid_response_marks_error_and_retains_document(
    deepseek_settings: Settings, passport_source: PassportSource, content: str
) -> None:
    before = passport_source.model_dump()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return completion_response(content)

    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(handler)
    ) as client:
        result = await PassportGenerator(client).generate(passport_source)
    assert result.status == "ERROR"
    assert result.passport is None
    assert result.error is not None
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True
    assert result.source.document_id == 42
    assert result.source.model_dump() == before
    assert passport_source.model_dump() == before
    assert calls == 1


async def test_failed_document_can_be_generated_again(
    deepseek_settings: Settings,
    passport_source: PassportSource,
    passport_payload: dict[str, Any],
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "{}" if calls == 1 else json.dumps(passport_payload)
        return completion_response(content)

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        generator = PassportGenerator(client)
        failed = await generator.generate(passport_source)
        retried = await generator.generate(failed.source)
    assert failed.status == "ERROR"
    assert retried.status == "GENERATED"
    assert failed.source == retried.source == passport_source


async def test_authentication_error_is_recorded_without_sensitive_response(
    deepseek_settings: Settings, passport_source: PassportSource
) -> None:
    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, text="Private provider response")
        ),
    ) as client:
        result = await PassportGenerator(client).generate(passport_source)
    assert result.status == "ERROR"
    assert result.source is passport_source
    assert result.error is not None
    assert result.error.code == "request_failed"
    assert result.error.status_code == 401
    assert result.error.retryable is False
    assert "Private provider response" not in result.error.message
    assert "unit-test-key" not in result.model_dump_json()


async def test_timeout_exhaustion_is_recorded_as_retryable_error(
    deepseek_settings: Settings, passport_source: PassportSource
) -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Sensitive connection details", request=request)

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        result = await PassportGenerator(client).generate(passport_source)
    assert result.status == "ERROR"
    assert result.error is not None
    assert result.error.retryable is True
    assert result.source is passport_source
    assert "Sensitive" not in result.error.message
