"""测试配置管理"""

import pytest

from hermes.core.config import Settings


def _build_settings(**overrides) -> Settings:
    """构建用于测试的 Settings 实例。"""
    defaults = {
        "DB_NAME": "hermes",
        "DB_PASSWORD": "test",
        "REDIS_PASSWORD": "test",
        "RABBITMQ_PASSWORD": "test",
        "MINIO_SECRET_KEY": "test",
        "LLM_API_KEY": "test",
        "LLM_BACKUP_API_KEY": "test",
        "EMBEDDING_API_KEY": "test",
        "JWT_SECRET": "test-secret-32chars-minimum!!",
        "ENCRYPTION_KEY": "jxmHOG1FgZJDFrKsVgOW0lQioiZ-M9S_VG3DRaRWM_c=",
        "LANGFUSE_SECRET_KEY": "test",
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestSettingsDefaults:
    """验证配置默认值"""

    def test_app_defaults(self):
        s = _build_settings()
        assert s.APP_NAME == "hermes"
        assert s.APP_VERSION == "0.1.0"
        assert s.ENV == "dev"
        assert s.DEBUG is False
        assert s.LOG_LEVEL == "INFO"

    def test_server_defaults(self):
        s = _build_settings()
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000
        assert s.WORKERS == 4
        assert s.CORS_ORIGINS == ["*"]

    def test_db_defaults(self):
        s = _build_settings()
        assert s.DB_HOST_WRITE == "localhost"
        assert s.DB_PORT == 5432
        assert s.DB_NAME == "hermes"
        assert s.DB_USER == "hermes"

    def test_jwt_defaults(self):
        s = _build_settings()
        assert s.JWT_ALGORITHM == "HS256"
        assert s.ACCESS_TOKEN_EXPIRE_SECONDS == 28800
        assert s.REFRESH_TOKEN_EXPIRE_SECONDS == 604800

    def test_security_defaults(self):
        s = _build_settings()
        assert s.MAX_LOGIN_ATTEMPTS == 5
        assert s.ACCOUNT_LOCK_MINUTES == 30
        assert s.MAX_UPLOAD_SIZE_MB == 500
        assert s.PASSWORD_MIN_LENGTH == 8


class TestDatabaseUrl:
    """验证数据库 URL 生成"""

    def test_database_url_format(self):
        s = _build_settings(
            DB_HOST_WRITE="localhost",
            DB_PORT=5432,
            DB_NAME="hermes",
            DB_USER="hermes",
            DB_PASSWORD="testpass",
        )
        url = s.database_url
        assert "postgresql+asyncpg://" in url
        assert "hermes:testpass@localhost:5432/hermes" in url

    def test_database_url_sync_format(self):
        s = _build_settings(
            DB_HOST_WRITE="localhost",
            DB_PORT=5432,
            DB_NAME="hermes",
            DB_USER="hermes",
            DB_PASSWORD="testpass",
        )
        url = s.database_url_sync
        assert "postgresql+psycopg2://" in url
        assert "hermes:testpass@localhost:5432/hermes" in url

    def test_database_url_with_custom_host(self):
        s = _build_settings(
            DB_HOST_WRITE="pg.example.com",
            DB_PORT=5433,
            DB_NAME="hermes_prod",
            DB_USER="prod_user",
            DB_PASSWORD="secret",
        )
        url = s.database_url
        assert "prod_user:secret@pg.example.com:5433/hermes_prod" in url


class TestCeleryBrokerUrl:
    """验证 Celery broker URL 生成"""

    def test_celery_url_format(self):
        s = _build_settings(
            RABBITMQ_HOST="rabbitmq",
            RABBITMQ_PORT=5672,
            RABBITMQ_USER="guest",
            RABBITMQ_PASSWORD="guest",
            RABBITMQ_VHOST="hermes",
        )
        url = s.celery_broker_url
        assert url == "amqp://guest:guest@rabbitmq:5672/hermes"

    def test_celery_url_with_vhost(self):
        s = _build_settings(
            RABBITMQ_HOST="mq.local",
            RABBITMQ_PORT=5672,
            RABBITMQ_USER="user",
            RABBITMQ_PASSWORD="pass",
            RABBITMQ_VHOST="hermes",
        )
        url = s.celery_broker_url
        assert url == "amqp://user:pass@mq.local:5672/hermes"


class TestCorsOrigins:
    """验证 CORS 解析"""

    def test_default(self):
        s = _build_settings()
        assert s.CORS_ORIGINS == ["*"]

    def test_comma_separated(self):
        s = _build_settings(CORS_ORIGINS="http://a.com,http://b.com")
        assert s.CORS_ORIGINS == ["http://a.com", "http://b.com"]

    def test_json_list(self):
        s = _build_settings(CORS_ORIGINS='["http://a.com","http://b.com"]')
        assert s.CORS_ORIGINS == ["http://a.com", "http://b.com"]

    def test_empty_string(self):
        s = _build_settings(CORS_ORIGINS="")
        assert s.CORS_ORIGINS == ["*"]


class TestEncryptionKeyValidation:
    """验证加密密钥校验"""

    def test_empty_key_allowed(self):
        s = _build_settings(ENCRYPTION_KEY="")
        assert s.ENCRYPTION_KEY.get_secret_value() == ""

    def test_valid_base64_key(self):
        import base64
        key = base64.b64encode(b"a" * 32).decode()
        s = _build_settings(ENCRYPTION_KEY=key)
        assert s.ENCRYPTION_KEY.get_secret_value() == key

    def test_invalid_base64(self):
        with pytest.raises(ValueError, match="base64"):
            _build_settings(ENCRYPTION_KEY="not-valid-base64!!!")

    def test_wrong_key_length(self):
        import base64
        key = base64.b64encode(b"short").decode()
        with pytest.raises(ValueError):
            _build_settings(ENCRYPTION_KEY=key)
