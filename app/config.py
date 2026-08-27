from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "研发效能日报生成助手"
    environment: str = "dev"
    api_key: str = ""
    max_request_bytes: int = 2_000_000
    llm_timeout: int = 60
    llm_retries: int = 2
    report_dir: str = "reports"
    database_path: str = "data/report.db"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("REPORT_ENV", "dev"),
            api_key=os.getenv("REPORT_API_KEY", "").strip(),
            max_request_bytes=int(os.getenv("REPORT_MAX_REQUEST_BYTES", "2000000")),
            llm_timeout=int(os.getenv("LLM_TIMEOUT", "60")),
            llm_retries=int(os.getenv("LLM_RETRIES", "2")),
            report_dir=os.getenv("REPORT_DIR", "reports"),
            database_path=os.getenv("REPORT_DATABASE", "data/report.db"),
        )

    def validate(self) -> None:
        if self.max_request_bytes <= 0 or self.max_request_bytes > 50_000_000:
            raise ValueError("REPORT_MAX_REQUEST_BYTES 必须在 1 到 50000000 之间")
        if self.environment == "production" and not self.api_key:
            raise ValueError("生产环境必须配置 REPORT_API_KEY")
