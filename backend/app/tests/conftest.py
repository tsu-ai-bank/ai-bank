from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from main import app
from src.core.config import Settings
from src.schemas.passport_generation import PassportSource


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def deepseek_settings() -> Settings:
    return Settings(
        deepseek_api_key=SecretStr("unit-test-key"),
        deepseek_timeout_seconds=7.5,
        deepseek_max_retries=2,
        deepseek_requests_per_minute=60,
    )


@pytest.fixture
def passport_payload() -> dict[str, Any]:
    return {
        "backlog": [
            {
                "number": number,
                "goal": f"Спринт {number}",
                "tasks": ["Сделать прототип"],
            }
            for number in range(1, 5)
        ],
        "roles": [{"name": "Разработчик", "responsibilities": ["Реализация API"]}],
        "effort": {"total_hours": 80, "explanation": "Четыре спринта по 20 часов"},
        "course_routing": [{"course": 2, "rationale": "Нужны основы программирования"}],
        "stack": {"no_code": ["Таблицы"], "web": ["Python", "FastAPI"]},
        "business_value": "Сокращение времени обработки заявок",
        "custdev_guide": ["Как сейчас обрабатываются заявки?"],
    }


@pytest.fixture
def passport_source() -> PassportSource:
    return PassportSource(
        document_id=42,
        faculty_id=1,
        text="Компании нужен инструмент для обработки заявок.",
        competencies=["Разработка программного обеспечения"],
    )
