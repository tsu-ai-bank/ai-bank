import asyncio
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from types import TracebackType
from typing import Self

import httpx

from src.core.config import Settings, get_settings
from src.core.constants import (
    DEEPSEEK_CHAT_COMPLETIONS_PATH,
    DEEPSEEK_MAX_OUTPUT_TOKENS,
    SECONDS_PER_MINUTE,
)

Sleep = Callable[[float], Awaitable[None]]


class DeepSeekRequestError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class DeepSeekResponseError(Exception):
    """The response is incomplete or is not a chat completion."""


class RequestRateLimiter:
    """Space request starts across concurrent calls to the same client."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._interval = SECONDS_PER_MINUTE / requests_per_minute
        self._sleep = sleep
        self._clock = clock
        self._next_request_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._next_request_at - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._next_request_at = self._clock() + self._interval


class DeepSeekClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        api_key = self._settings.deepseek_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ValueError("Set DEEPSEEK_API_KEY before creating a DeepSeek client")
        self._sleep = sleep
        self._limiter = RequestRateLimiter(
            self._settings.deepseek_requests_per_minute, sleep=sleep, clock=clock
        )
        self._http = httpx.AsyncClient(
            base_url=f"{str(self._settings.deepseek_base_url).rstrip('/')}/",
            headers={"Authorization": f"Bearer {api_key.get_secret_value().strip()}"},
            timeout=httpx.Timeout(self._settings.deepseek_timeout_seconds),
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": DEEPSEEK_MAX_OUTPUT_TOKENS,
            "stream": False,
        }
        for attempt in range(self._settings.deepseek_max_retries + 1):
            await self._limiter.wait()
            try:
                response = await self._http.post(
                    DEEPSEEK_CHAT_COMPLETIONS_PATH, json=payload
                )
            except httpx.TransportError:
                if attempt == self._settings.deepseek_max_retries:
                    raise DeepSeekRequestError(
                        "DeepSeek connection failed or timed out", retryable=True
                    ) from None
                await self._sleep(self._retry_delay(attempt))
                continue

            retryable = response.status_code == 429 or response.status_code >= 500
            if response.is_error:
                if retryable and attempt < self._settings.deepseek_max_retries:
                    await self._sleep(
                        self._retry_delay(attempt, response.headers.get("Retry-After"))
                    )
                    continue
                raise DeepSeekRequestError(
                    f"DeepSeek request failed (HTTP {response.status_code})",
                    retryable=retryable,
                    status_code=response.status_code,
                )
            return self._read_content(response)
        raise AssertionError("Retry loop exited without a response")

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> float:
        fallback = self._settings.deepseek_retry_base_seconds * 2**attempt
        if retry_after is None:
            return fallback
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                seconds = (retry_at - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return fallback
        if not math.isfinite(seconds):
            return fallback
        return max(fallback, seconds)

    @staticmethod
    def _read_content(response: httpx.Response) -> str:
        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop":
                raise DeepSeekResponseError("DeepSeek did not finish the response")
            if not isinstance(content, str) or not content.strip():
                raise DeepSeekResponseError("DeepSeek returned empty content")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise DeepSeekResponseError("Invalid DeepSeek response envelope") from None
        return content
