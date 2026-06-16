"""
赫尔墨斯（Hermes）系统配置管理

基于 Pydantic Settings，支持 .env 文件 / K8s ConfigMap+Secret / 环境变量注入。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file() -> str | None:
    """根据 ENV 环境变量选择对应的 .env 文件，不存在则回退到 .env。"""
    env = os.getenv("ENV", "dev")
    candidates = [
        Path(__file__).resolve().parents[2] / f".env.{env}",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


class Settings(BaseSettings):
    """全局配置，所有字段均可从环境变量 / .env 文件读取。

    K8s 部署时通过 ConfigMap (非敏感) + Secret (敏感) 注入。
    """

    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用 ────────────────────────────────────────────────────
    APP_NAME: str = "hermes"
    APP_VERSION: str = "0.1.0"
    ENV: Literal["dev", "staging", "prod"] = "dev"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── 服务器 ──────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    # ── 服务器 字段校验 ──────────────────────────────────────────
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """将 CORS_ORIGINS 标准化为 list[str]——无论来自 env JSON、逗号分隔字符串还是裸字符串均可正确解析。"""
        if v is None:
            return ["*"]
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            if v:
                return [x.strip() for x in v.split(",") if x.strip()]
        return ["*"]

    # ── 数据库 (PostgreSQL 16 + pgvector) ──────────────────────
    DB_HOST_WRITE: str = "localhost"
    DB_HOST_READ: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "hermes"
    DB_USER: str = "hermes"
    DB_PASSWORD: SecretStr = SecretStr("")
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:"
            f"{self.DB_PASSWORD.get_secret_value()}"
            f"@{self.DB_HOST_WRITE}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DB_USER}:"
            f"{self.DB_PASSWORD.get_secret_value()}"
            f"@{self.DB_HOST_WRITE}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ── Redis Cluster ──────────────────────────────────────────
    REDIS_CLUSTER_NODES: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: SecretStr = SecretStr("")
    REDIS_MAX_CONNECTIONS: int = 50

    # ── RabbitMQ ───────────────────────────────────────────────
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: SecretStr = SecretStr("guest")
    RABBITMQ_VHOST: str = "/"

    @property
    def celery_broker_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:"
            f"{self.RABBITMQ_PASSWORD.get_secret_value()}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{self.RABBITMQ_VHOST}"
        )

    # ── Elasticsearch ──────────────────────────────────────────
    ES_HOSTS: str = "http://localhost:9200"
    ES_INDEX_PREFIX: str = "hermes"

    # ── MinIO ──────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: SecretStr = SecretStr("minioadmin")
    MINIO_BUCKET: str = "hermes"
    MINIO_SECURE: bool = False

    # ── LLM ────────────────────────────────────────────────────
    LLM_API_BASE: str = "https://api.deepseek.com"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "deepseek-v4-pro"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 16384
    LLM_REQUEST_TIMEOUT: int = 120

    # 备用 LLM
    LLM_BACKUP_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_BACKUP_API_KEY: SecretStr = SecretStr("")
    LLM_BACKUP_MODEL: str = "qwen3.7-plus"

    # ── Embedding ──────────────────────────────────────────────
    EMBEDDING_API_BASE: str = "https://api.lingyaai.cn/v1"
    EMBEDDING_API_KEY: SecretStr = SecretStr("")
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIM: int = 1536

    # ── JWT ────────────────────────────────────────────────────
    JWT_SECRET: SecretStr = SecretStr("change-me-to-a-random-string-at-least-32-chars")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 28800  # 8 hours
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 604800  # 7 days

    # ── 加密 (AES-256-GCM) ────────────────────────────────────
    ENCRYPTION_KEY: SecretStr = SecretStr("")  # 32 bytes base64-encoded

    # ── 安全 ───────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 30
    MAX_UPLOAD_SIZE_MB: int = 500
    PASSWORD_MIN_LENGTH: int = 8

    # ── 速率限制 ───────────────────────────────────────────────
    RATE_LIMIT_GLOBAL_RPS: int = 1000
    RATE_LIMIT_USER_RPM: int = 100
    RATE_LIMIT_LLM_RPS: int = 50

    # ── 数据分层 ───────────────────────────────────────────────
    HOT_DATA_RETENTION_DAYS: int = 90
    WARM_DATA_RETENTION_DAYS: int = 730
    COLD_DATA_RETENTION_YEARS: int = 10

    # ── 可观测性 ───────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: SecretStr = SecretStr("")
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    JAEGER_HOST: str = "localhost"
    JAEGER_PORT: int = 6831
    SENTRY_DSN: str = ""

    @field_validator("ENCRYPTION_KEY", mode="before")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if not v:
            return v
        import base64

        try:
            # Fernet uses URL-safe base64; accept both standard (+/) and URL-safe (-_)
            key = base64.b64decode(v, altchars=b"-_", validate=True)
            if len(key) != 32:
                raise ValueError("ENCRYPTION_KEY must decode to 32 bytes")
        except Exception:
            raise ValueError("ENCRYPTION_KEY must be a valid base64-encoded 32-byte key")
        return v


# 全局单例
settings = Settings()
