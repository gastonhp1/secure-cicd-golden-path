from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from demo_api.logging import JsonFormatter
from demo_api.main import create_app
from demo_api.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", version="1.2.3", git_sha="abc123", pod_name="pod-0", api_key=None)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as c:
        yield c


def test_probes(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_readiness_is_false_before_startup(settings: Settings) -> None:
    # Without entering the context manager the lifespan has not run.
    client = TestClient(create_app(settings))
    assert client.get("/readyz").status_code == 503


def test_info_never_leaks_secret() -> None:
    s = Settings(env="dev", version="1.0.0", git_sha="x", pod_name="p", api_key="s3cr3t")
    with TestClient(create_app(s)) as c:
        body = c.get("/api/v1/info").json()
    assert body["secret_loaded"] is True
    assert "s3cr3t" not in json.dumps(body)


def test_info_reports_build_metadata(client: TestClient) -> None:
    body = client.get("/api/v1/info").json()
    assert body == {
        "service": "demo-api",
        "version": "1.2.3",
        "git_sha": "abc123",
        "env": "test",
        "pod": "pod-0",
        "secret_loaded": False,
    }


def test_work_validates_bounds(client: TestClient) -> None:
    assert client.get("/api/v1/work", params={"ms": 1}).json() == {"slept_ms": 1}
    assert client.get("/api/v1/work", params={"ms": -1}).status_code == 422
    assert client.get("/api/v1/work", params={"ms": 999_999}).status_code == 422


def test_metrics_use_route_templates_and_skip_probes(client: TestClient) -> None:
    client.get("/api/v1/info")
    client.get("/healthz")
    client.get("/does-not-exist")
    metrics = client.get("/metrics").text

    assert 'http_requests_total{method="GET",route="/api/v1/info",status="200"} 1.0' in metrics
    assert 'route="unmatched"' in metrics
    assert "/healthz" not in metrics
    assert 'app_build_info{env="test",git_sha="abc123",version="1.2.3"} 1.0' in metrics


def test_json_log_formatter_includes_fields() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.fields = {"route": "/x", "status": 200}
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hello"
    assert out["level"] == "info"
    assert out["route"] == "/x"
    assert out["status"] == 200


def test_json_log_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    out = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in out["exc"]
