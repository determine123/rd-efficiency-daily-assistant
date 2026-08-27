from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable

from .config import Settings
from .main import generate_report
from .workflow import build_workflow

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover
    FastAPI = None

logger = logging.getLogger("report_assistant")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
settings = Settings.from_env()


if FastAPI is not None:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="基于 Git、新闻和证据校验生成研发技术日报。",
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return JSONResponse(status_code=413, content={"detail": "请求体超过大小限制", "request_id": request_id})
        if settings.environment == "production" and request.url.path not in {"/health", "/ready"}:
            if request.headers.get("X-API-Key", "") != settings.api_key:
                return JSONResponse(status_code=401, content={"detail": "缺少或错误的 API Key", "request_id": request_id})
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
            response = JSONResponse(status_code=500, content={"detail": "服务内部错误", "request_id": request_id})
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "report-assistant"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        settings.validate()
        return {"status": "ready"}

    @app.post("/generate")
    def generate(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            report, metadata = generate_report(payload)
            return {"report": report, "validation": metadata["validation"], "evidence_ledger": metadata["evidence_ledger"], "llm_used": metadata.get("llm_used", False), "llm_error": metadata.get("llm_error", "")}
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/workflow/invoke")
    def invoke_workflow(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = build_workflow().invoke({"input_data": payload})
            return {"report": result["report"], "validation": result["validation"], "evidence_ledger": result["evidence_ledger"], "llm_used": result.get("llm_used", False), "llm_error": result.get("llm_error", "")}
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
else:
    app = None


def run() -> None:
    if app is None:
        raise RuntimeError("未安装 FastAPI。请执行 pip install -r requirements.txt")
    import uvicorn
    uvicorn.run(app, host=os.getenv("REPORT_HOST", "127.0.0.1"), port=int(os.getenv("REPORT_PORT", "8000")))


if __name__ == "__main__":
    run()
