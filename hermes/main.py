"""
赫尔墨斯（Hermes）FastAPI 应用入口

启动方式：
    uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from hermes.api.v1.router import api_router
from hermes.core.config import settings
from hermes.core.exceptions import HermesError
from hermes.core.logging import get_logger, setup_logging
from hermes.core.observability import get_langfuse, shutdown
from hermes.middleware.audit import AuditMiddleware
from hermes.middleware.langfuse_trace import LangfuseTraceMiddleware
from hermes.middleware.rate_limit import RateLimitMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    setup_logging()
    logger.info("hermes_starting", version=settings.APP_VERSION, env=settings.ENV)

    # 初始化 Langfuse（可选依赖，优雅降级）
    try:
        lf = get_langfuse()
        if lf:
            lf.auth_check()
            logger.info("langfuse_connected", host=settings.LANGFUSE_BASE_URL)
        else:
            logger.info("langfuse_not_configured", message="Langfuse 未配置，分布式追踪功能关闭")
    except Exception as e:
        logger.warning("langfuse_unavailable", error=str(e), message="Langfuse 不可用，分布式追踪功能降级")

    # 初始化 Redis 连接池（可选依赖，仅当配置了 Redis 时才初始化）
    try:
        import redis.asyncio as redis
        redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_CLUSTER_NODES.split(",")[0],
            password=settings.REDIS_PASSWORD.get_secret_value() or None,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        app.state.redis = redis.Redis(connection_pool=redis_pool)
        await app.state.redis.ping()
        logger.info("redis_connected", nodes=settings.REDIS_CLUSTER_NODES)
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e), message="Redis 未配置或不可用，相关功能降级")
        app.state.redis = None

    # 初始化 Elasticsearch 客户端（可选依赖）
    try:
        from elasticsearch import AsyncElasticsearch
        es_client = AsyncElasticsearch(settings.ES_HOSTS.split(","))
        app.state.es = es_client
        if await es_client.ping():
            logger.info("elasticsearch_connected", hosts=settings.ES_HOSTS)
        else:
            logger.warning("elasticsearch_ping_failed")
            app.state.es = None
    except Exception as e:
        logger.warning("elasticsearch_unavailable", error=str(e),
                       message="Elasticsearch 未配置或不可用，全文搜索降级为数据库搜索")
        app.state.es = None

    # 初始化 MinIO 客户端（可选依赖）
    try:
        from minio import Minio
        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY.get_secret_value(),
            secure=settings.MINIO_SECURE,
        )
        if minio_client.bucket_exists(settings.MINIO_BUCKET):
            app.state.minio = minio_client
            logger.info("minio_connected", endpoint=settings.MINIO_ENDPOINT, bucket=settings.MINIO_BUCKET)
        else:
            minio_client.make_bucket(settings.MINIO_BUCKET)
            app.state.minio = minio_client
            logger.info("minio_bucket_created", bucket=settings.MINIO_BUCKET)
    except Exception as e:
        logger.warning("minio_unavailable", error=str(e), message="MinIO 未配置或不可用，文件存储功能降级")
        app.state.minio = None

    yield

    # 优雅关闭连接
    logger.info("hermes_stopping")

    # 刷新 Langfuse 缓冲区
    try:
        await shutdown()
    except Exception as e:
        logger.warning("langfuse_shutdown_error", error=str(e))

    if app.state.redis:
        try:
            await app.state.redis.aclose()
            logger.info("redis_disconnected")
        except Exception as e:
            logger.warning("redis_close_error", error=str(e))

    if hasattr(app.state, "es") and app.state.es:
        try:
            await app.state.es.close()
            logger.info("elasticsearch_disconnected")
        except Exception as e:
            logger.warning("es_close_error", error=str(e))

    logger.info("hermes_stopped")


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
    # 2. Langfuse 分布式追踪（包含审计 trace_id，自动继承上游上下文）
    app.add_middleware(LangfuseTraceMiddleware)
    # 3. 速率限制
    app.add_middleware(RateLimitMiddleware)
    # 4. CORS（最外层）
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

    # ── 前端静态文件（仅在 dist 存在时启用） ──────────────────
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend-dist"
    if FRONTEND_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str, request: Request):
            """SPA 回退：非 API 路径返回 index.html"""
            file_path = FRONTEND_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
