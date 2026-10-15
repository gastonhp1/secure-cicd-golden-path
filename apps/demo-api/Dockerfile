# syntax=docker/dockerfile:1.10

# ---- build: resolve and install dependencies into an isolated venv ----------
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /venv
COPY pyproject.toml ./
COPY src ./src
# pip isn't needed at runtime and vendors its own urllib3/msgpack/setuptools,
# which the scan would flag in the copied venv.
RUN /venv/bin/pip install . \
 && /venv/bin/pip uninstall -y pip

# ---- runtime: no compilers, no pip, non-root ---------------------------------
FROM python:3.13-slim AS runtime

ARG APP_VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.source="https://github.com/gastonhp1/secure-cicd-golden-path" \
      org.opencontainers.image.description="demo-api reference service" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

# Drop the package manager from the final image: smaller attack surface and
# fewer findings in the vulnerability scan.
RUN pip uninstall -y pip setuptools wheel 2>/dev/null || true \
 && groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /venv /venv

ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

USER 10001:10001
EXPOSE 8080

# Exec form: uvicorn is PID 1 and receives SIGTERM directly for graceful shutdown.
ENTRYPOINT ["uvicorn", "demo_api.main:app", "--host", "0.0.0.0", "--port", "8080", \
            "--proxy-headers", "--forwarded-allow-ips=*", "--timeout-graceful-shutdown", "20"]
