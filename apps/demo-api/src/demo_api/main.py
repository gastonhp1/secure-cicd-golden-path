from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from demo_api import logging as app_logging
from demo_api.settings import Settings

log = logging.getLogger("demo_api")

# Paths that should not pollute request metrics or logs.
_PROBE_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app_logging.configure(settings.log_level)

    registry = CollectorRegistry()
    requests_total = Counter(
        "http_requests_total",
        "HTTP requests by route, method and status.",
        ["route", "method", "status"],
        registry=registry,
    )
    request_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency by route.",
        ["route", "method"],
        # Buckets around the SLO threshold (300 ms) so burn-rate alerts are precise.
        buckets=(0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0),
        registry=registry,
    )
    build_info = Gauge(
        "app_build_info",
        "Constant 1, labelled with build metadata.",
        ["version", "git_sha", "env"],
        registry=registry,
    )
    build_info.labels(settings.version, settings.git_sha, settings.env).set(1)

    state = {"ready": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["ready"] = True
        log.info("startup", extra={"fields": {"version": settings.version, "env": settings.env}})
        yield
        # Fail readiness first so the Service stops routing here before we exit.
        state["ready"] = False
        log.info("shutdown")

    app = FastAPI(title="demo-api", version=settings.version, lifespan=lifespan)

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            path = request.url.path
            if path not in _PROBE_PATHS:
                # Label by route template (/api/v1/items/{id}), never the raw path,
                # to keep metric cardinality bounded.
                route = request.scope.get("route")
                template = route.path if isinstance(route, APIRoute) else "unmatched"
                elapsed = time.perf_counter() - start
                requests_total.labels(template, request.method, str(status)).inc()
                request_seconds.labels(template, request.method).observe(elapsed)
                log.info(
                    "request",
                    extra={
                        "fields": {
                            "method": request.method,
                            "route": template,
                            "status": status,
                            "duration_ms": round(elapsed * 1000, 2),
                        }
                    },
                )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(response: Response) -> dict[str, str]:
        if not state["ready"]:
            response.status_code = 503
            return {"status": "not-ready"}
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/v1/info")
    async def info() -> dict[str, object]:
        return {
            "service": "demo-api",
            "version": settings.version,
            "git_sha": settings.git_sha,
            "env": settings.env,
            "pod": settings.pod_name,
            # Proves the Key Vault -> External Secrets -> env var path works,
            # without ever exposing the value.
            "secret_loaded": settings.api_key is not None,
        }

    @app.get("/api/v1/work")
    async def work(ms: int = Query(default=50, ge=0)) -> dict[str, int]:
        """Simulated latency: handy to exercise HPA, SLO alerts and dashboards."""
        if ms > settings.max_work_ms:
            raise HTTPException(status_code=422, detail=f"ms must be <= {settings.max_work_ms}")
        await asyncio.sleep(ms / 1000)
        return {"slept_ms": ms}

    return app


app = create_app()
