"""Opt-in integration check with a strict budget of one external request."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import dotenv_values
from pydantic import SecretStr

from src.core.config import Settings
from src.schemas.passport_generation import PassportSource
from src.services.deepseek import DeepSeekClient
from src.services.passport_generation import PassportGenerator

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_DEEPSEEK_LIVE_TEST") != "1",
        reason="Requires explicit RUN_DEEPSEEK_LIVE_TEST=1 and a local API key",
    ),
]


class SingleRequestTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.request_count = 0
        self.status_code: int | None = None
        self.response_model: str | None = None
        self.finish_reason: str | None = None
        self.content: str | None = None
        self.provider_error: Any = None
        self.usage: dict[str, Any] | None = None
        self._transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.request_count >= 1:
            raise AssertionError("A second DeepSeek request is forbidden in this test")
        assert request.url.scheme == "https"
        assert request.url.host == "api.deepseek.com"
        assert request.url.path == "/chat/completions"
        self.request_count += 1
        response = await self._transport.handle_async_request(request)
        self.status_code = response.status_code
        await response.aread()
        try:
            payload = response.json()
            provider_error = payload.get("error")
            if provider_error is not None:
                token = request.headers["Authorization"].removeprefix("Bearer ")
                sanitized = json.dumps(provider_error, ensure_ascii=False).replace(
                    token, "[REDACTED]"
                )
                self.provider_error = json.loads(sanitized)
            self.response_model = payload.get("model")
            self.usage = payload.get("usage")
            choices = payload.get("choices", [])
            if choices:
                self.finish_reason = choices[0].get("finish_reason")
                self.content = choices[0].get("message", {}).get("content")
        except (ValueError, TypeError, AttributeError, IndexError):
            pass
        return response

    async def aclose(self) -> None:
        await self._transport.aclose()


async def test_real_passport_generation_uses_exactly_one_request() -> None:
    values = dotenv_values(REPOSITORY_ROOT / ".env")
    api_key = values.get("DEEPSEEK_API_KEY")
    assert api_key, "Set DEEPSEEK_API_KEY in the ignored repository-root .env"
    configuration: dict[str, Any] = {
        "deepseek_api_key": SecretStr(api_key),
        "deepseek_max_retries": 0,
    }
    if model := values.get("DEEPSEEK_MODEL"):
        configuration["deepseek_model"] = model
    settings = Settings.model_validate(configuration)
    source = PassportSource(
        document_id=1,
        faculty_id=1,
        text=(
            "Учебный пример: небольшой компании нужен веб-сервис учёта заявок. "
            "Сотрудники создают заявки, назначают исполнителей и отслеживают статус. "
            "Заказчик хочет сократить время обработки заявок. Подготовь компактный "
            "паспорт учебного проекта: четыре спринта с номерами 1, 2, 3, 4."
        ),
        competencies=[
            "Разработка веб-приложений",
            "Проектирование баз данных",
            "Тестирование программного обеспечения",
        ],
    )
    transport = SingleRequestTransport()
    async with DeepSeekClient(settings, transport=transport) as client:
        result = await PassportGenerator(client).generate(source)

    report = {
        "request_count": transport.request_count,
        "http_status": transport.status_code,
        "requested_model": settings.deepseek_model,
        "response_model": transport.response_model,
        "finish_reason": transport.finish_reason,
        "usage": transport.usage,
        "status": result.status,
        "error": result.error.model_dump() if result.error else None,
        "provider_error": transport.provider_error,
        "passport": result.passport.model_dump() if result.passport else None,
        "raw_content": transport.content,
        "source_preserved": result.source == source,
    }
    artifact = REPOSITORY_ROOT / ".artifacts" / "deepseek-live-result.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"passport", "raw_content"}
            },
            ensure_ascii=False,
        )
    )
    assert transport.request_count == 1
    assert transport.status_code == 200
    assert result.status == "GENERATED", report["error"]
    assert result.passport is not None
    assert len(result.passport.model_dump()) == 7
    assert result.source == source
