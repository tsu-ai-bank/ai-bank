import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from src.core.config import Settings
from src.services.deepseek import (
    DeepSeekClient,
    DeepSeekRequestError,
    DeepSeekResponseError,
)
from tests.fakes import FakeClock, completion_response

pytestmark = pytest.mark.anyio


async def test_request_uses_configured_key_model_and_timeout(
    deepseek_settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer unit-test-key"
        assert set(request.extensions["timeout"].values()) == {7.5}
        payload = json.loads(request.content)
        assert payload["model"] == deepseek_settings.deepseek_model
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is False
        assert payload["messages"] == [
            {"role": "system", "content": "Return JSON"},
            {"role": "user", "content": "Source text"},
        ]
        return completion_response('{"ok": true}')

    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(handler)
    ) as client:
        content = await client.complete_json(
            system_prompt="Return JSON", user_prompt="Source text"
        )
    assert json.loads(content) == {"ok": True}


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
async def test_transient_http_error_is_retried(
    deepseek_settings: Settings, status_code: int
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status_code)
        return completion_response("{}")

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        assert await client.complete_json(system_prompt="JSON", user_prompt="x") == "{}"
    assert calls == 2
    assert clock.sleeps == [1.0]


@pytest.mark.parametrize("status_code", [400, 401, 402, 403, 422])
async def test_permanent_http_error_is_not_retried(
    deepseek_settings: Settings, status_code: int
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text="Private upstream response")

    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(DeepSeekRequestError) as caught:
            await client.complete_json(system_prompt="JSON", user_prompt="x")
    assert calls == 1
    assert caught.value.status_code == status_code
    assert caught.value.retryable is False
    assert "Private upstream response" not in str(caught.value)
    assert "unit-test-key" not in str(caught.value)


async def test_retry_count_is_bounded_and_backoff_increases(
    deepseek_settings: Settings,
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        with pytest.raises(DeepSeekRequestError) as caught:
            await client.complete_json(system_prompt="JSON", user_prompt="x")
    assert calls == 3
    assert clock.sleeps == [1.0, 2.0]
    assert caught.value.retryable is True


@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError]
)
async def test_transport_failures_are_retried(
    deepseek_settings: Settings, failure: type[httpx.TransportError]
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise failure("Sensitive connection details", request=request)
        return completion_response("{}")

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        assert await client.complete_json(system_prompt="JSON", user_prompt="x") == "{}"
    assert calls == 2


async def test_exhausted_timeout_returns_sanitized_error(
    deepseek_settings: Settings,
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("Sensitive connection details", request=request)

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        with pytest.raises(DeepSeekRequestError) as caught:
            await client.complete_json(system_prompt="JSON", user_prompt="x")
    assert calls == 3
    assert caught.value.retryable is True
    assert "Sensitive" not in str(caught.value)


@pytest.mark.parametrize(
    "retry_after,expected", [("4", 4.0), ("bad", 1.0), ("nan", 1.0)]
)
async def test_retry_after_is_respected(
    deepseek_settings: Settings, retry_after: str, expected: float
) -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return completion_response("{}")

    async with DeepSeekClient(
        deepseek_settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        await client.complete_json(system_prompt="JSON", user_prompt="x")
    assert clock.sleeps == [expected]


async def test_concurrent_requests_and_retries_share_rate_limit(
    deepseek_settings: Settings,
) -> None:
    clock = FakeClock()
    starts: list[float] = []
    settings = deepseek_settings.model_copy(update={"deepseek_requests_per_minute": 30})

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock.now)
        if len(starts) == 1:
            return httpx.Response(503)
        return completion_response("{}")

    async with DeepSeekClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.monotonic,
    ) as client:
        await asyncio.gather(
            client.complete_json(system_prompt="JSON", user_prompt="first"),
            client.complete_json(system_prompt="JSON", user_prompt="second"),
        )
    assert starts == [0.0, 2.0, 4.0]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, text="not JSON"),
        completion_response("   "),
        completion_response("{}", finish_reason="length"),
        completion_response("{}", finish_reason="content_filter"),
    ],
)
async def test_invalid_completion_envelope_is_rejected(
    deepseek_settings: Settings, response: httpx.Response
) -> None:
    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(lambda request: response)
    ) as client:
        with pytest.raises(DeepSeekResponseError):
            await client.complete_json(system_prompt="JSON", user_prompt="x")


@pytest.mark.parametrize("api_key", [None, SecretStr(""), SecretStr("   ")])
async def test_missing_key_is_rejected_without_network(
    api_key: SecretStr | None,
) -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekClient(Settings(deepseek_api_key=api_key))


async def test_cancellation_is_not_retried(deepseek_settings: Settings) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    async with DeepSeekClient(
        deepseek_settings, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(asyncio.CancelledError):
            await client.complete_json(system_prompt="JSON", user_prompt="x")
    assert calls == 1
