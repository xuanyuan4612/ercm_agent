"""
赫尔墨斯（Hermes）FastAPI 应用入口

启动方式：
    uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from hermes.api.v1.router import api_router
from hermes.core.config import settings
from hermes.core.exceptions import HermesError
from hermes.core.logging import get_logger, setup_logging
from hermes.middleware.audit import AuditMiddleware
from hermes.middleware.rate_limit import RateLimitMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    setup_logging()
    logger.info("hermes_starting", version=settings.APP_VERSION, env=settings.ENV)
    # TODO: 初始化 Redis 连接池
    # TODO: 初始化 Elasticsearch 客户端
    # TODO: 初始化 MinIO 客户端
    yield
    logger.info("hermes_stopping")
    # TODO: 优雅关闭连接


def create_app() -> FastAPI:
    app = FastAPI(
        title="赫尔墨斯（Hermes）风险控制 AI 智能体",
        description="面向科沃斯集团的企业级风控 AI 智能体系统",
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── 中间件注册（顺序重要：内→外 = 请求处理顺序） ──────────
    # 1. 审计日志（最内层：需要 trace_id 贯穿整个请求）
    app.add_middleware(AuditMiddleware)
    # 2. 速率限制
    app.add_middleware(RateLimitMiddleware)
    # 3. CORS（最外层）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 异常处理器 ───────────────────────────────────────────
    @app.exception_handler(HermesError)
    async def hermes_exception_handler(request: Request, exc: HermesError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        trace_id = getattr(request.state, "trace_id", None)
        logger.exception(
            "unhandled_error",
            trace_id=trace_id,
            path=request.url.path,
            error=str(exc),
        )
        return ORJSONResponse(
            status_code=500,
            content={"code": 50000, "message": "服务器内部错误", "detail": str(exc) if settings.DEBUG else None},
        )

    # ── 路由注册 ─────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # 健康检查
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
