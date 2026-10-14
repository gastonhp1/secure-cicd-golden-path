from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read once from the environment (12-factor)."""

    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "dev"))
    git_sha: str = field(default_factory=lambda: os.getenv("GIT_SHA", "unknown"))
    pod_name: str = field(default_factory=lambda: os.getenv("POD_NAME", "local"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "info").upper())
    # Injected from Key Vault by External Secrets in the cluster. Never logged or returned.
    api_key: str | None = field(default_factory=lambda: os.getenv("DEMO_API_KEY") or None)
    max_work_ms: int = field(default_factory=lambda: int(os.getenv("MAX_WORK_MS", "2000")))
