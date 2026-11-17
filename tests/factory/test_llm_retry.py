"""The 429 wrapper is deterministic: no network, no sleeping."""

import pytest
from google.genai.errors import ClientError

from factory_app import config
from factory_app.llm import (
    RateLimitExhausted,
    call_with_retry,
    is_rate_limited,
    retry_delay_hint,
)


def _quota_error(retry_delay: str | None = None) -> ClientError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}]
    body = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "quota",
            "details": details if retry_delay else [],
        }
    }
    return ClientError(429, body)


def test_429_is_retried_then_succeeds_and_retries_are_logged():
    calls, retries, sleeps = [], [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _quota_error()
        return "ok"

    result = call_with_retry(flaky, on_retry=retries.append, sleep=sleeps.append, rng=lambda: 0)
    assert result == "ok"
    assert len(calls) == 3
    assert [r["attempt"] for r in retries] == [1, 2]
    assert sleeps == [config.RETRY_BASE_DELAY_S, config.RETRY_BASE_DELAY_S * 2]  # exponential


def test_server_retry_delay_hint_is_honoured():
    err = _quota_error("27s")
    assert is_rate_limited(err)
    assert retry_delay_hint(err) == 27.0
    sleeps = []
    attempts = iter([err])

    def once():
        for e in attempts:
            raise e
        return "ok"

    call_with_retry(once, sleep=sleeps.append, rng=lambda: 0)
    assert sleeps == [27.0]


def test_persistent_429_raises_resumable_error():
    def always():
        raise _quota_error()

    with pytest.raises(RateLimitExhausted):
        call_with_retry(always, sleep=lambda _: None, rng=lambda: 0, max_attempts=3)


def test_503_overload_wrapped_by_adk_is_retried_and_labelled():
    from google.genai.errors import ServerError

    class AdkWrapper(Exception):
        pass

    calls, retries = [], []

    def overloaded_once():
        calls.append(1)
        if len(calls) == 1:
            try:
                raise ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
            except ServerError as inner:
                raise AdkWrapper("Dynamic node failed") from inner
        return "ok"

    assert call_with_retry(overloaded_once, on_retry=retries.append, sleep=lambda _: None) == "ok"
    assert retries[0]["error"] == "503"


def test_daily_quota_pauses_immediately_instead_of_retrying():
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
    calls = []

    def daily():
        calls.append(1)
        raise ClientError(429, body)

    with pytest.raises(RateLimitExhausted, match="daily quota"):
        call_with_retry(daily, sleep=lambda _: None)
    assert len(calls) == 1


def test_per_minute_quota_is_retried_and_quota_id_logged():
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}
    calls, retries = [], []

    def per_minute_once():
        calls.append(1)
        if len(calls) == 1:
            raise ClientError(429, body)
        return "ok"

    call_with_retry(per_minute_once, on_retry=retries.append, sleep=lambda _: None)
    assert retries[0]["quota"].startswith("GenerateRequestsPerMinute")


def test_non_429_errors_are_not_retried():
    calls = []

    def boom():
        calls.append(1)
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        call_with_retry(boom, sleep=lambda _: None)
    assert len(calls) == 1


def test_vertex_mode_is_refused(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    with pytest.raises(RuntimeError, match="Developer API"):
        config.ensure_api_key()


def test_gemini_api_key_is_accepted(monkeypatch):
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    config.ensure_api_key()
    import os

    assert os.environ["GOOGLE_API_KEY"] == "test-not-a-real-key"
