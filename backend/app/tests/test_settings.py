import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


@pytest.mark.parametrize(
    "values",
    [
        {"deepseek_timeout_seconds": 0},
        {"deepseek_timeout_seconds": float("inf")},
        {"deepseek_requests_per_minute": 0},
        {"deepseek_max_retries": -1},
        {"deepseek_max_retries": 11},
        {"deepseek_retry_base_seconds": -1},
        {"deepseek_base_url": "not-a-url"},
    ],
)
def test_invalid_deepseek_configuration_is_rejected(values: dict) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_settings_read_environment_and_keep_frozen_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_MODEL", "configured-model")
    monkeypatch.setenv("DEEPSEEK_REQUESTS_PER_MINUTE", "12")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-test-key")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.deepseek_model == "configured-model"
        assert settings.deepseek_requests_per_minute == 12
        assert get_settings() is settings
        assert "unit-test-key" not in repr(settings)
        with pytest.raises(ValidationError):
            settings.deepseek_model = "changed"
        monkeypatch.setenv("DEEPSEEK_MODEL", "new-model")
        assert get_settings().deepseek_model == "configured-model"
        get_settings.cache_clear()
        assert get_settings().deepseek_model == "new-model"
    finally:
        get_settings.cache_clear()
