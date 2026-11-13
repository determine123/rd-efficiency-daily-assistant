from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "研发效能日报生成助手"
    environment: str = "dev"
    api_key: str = ""
    max_request_bytes: int = 2_000_000
    max_concurrent_requests: int = 4
    request_timeout_seconds: float = 120.0
    llm_timeout: int = 60
    llm_retries: int = 2
    report_dir: str = "reports"
    database_path: str = "data/report.db"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            environment=os.getenv("REPORT_ENV", "dev"),
            api_key=os.getenv("REPORT_API_KEY", "").strip(),
            max_request_bytes=int(os.getenv("REPORT_MAX_REQUEST_BYTES", "2000000")),
            max_concurrent_requests=int(os.getenv("REPORT_MAX_CONCURRENT_REQUESTS", "4")),
            request_timeout_seconds=float(os.getenv("REPORT_REQUEST_TIMEOUT_SECONDS", "120")),
            llm_timeout=int(os.getenv("LLM_TIMEOUT", "60")),
            llm_retries=int(os.getenv("LLM_RETRIES", "2")),
            report_dir=os.getenv("REPORT_DIR", "reports"),
            database_path=os.getenv("REPORT_DATABASE", "data/report.db"),
        )

    def validate(self) -> None:
        if self.max_request_bytes <= 0 or self.max_request_bytes > 50_000_000:
            raise ValueError("REPORT_MAX_REQUEST_BYTES 必须在 1 到 50000000 之间")
        if not 1 <= self.max_concurrent_requests <= 64:
            raise ValueError("REPORT_MAX_CONCURRENT_REQUESTS 必须在 1 到 64 之间")
        if not 0 < self.request_timeout_seconds <= 3600:
            raise ValueError("REPORT_REQUEST_TIMEOUT_SECONDS 必须大于 0 且不超过 3600")
        if self.environment == "production" and not self.api_key:
            raise ValueError("生产环境必须配置 REPORT_API_KEY")
