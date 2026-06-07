"""测试配置管理"""

from hermes.core.config import Settings


def test_settings_defaults():
    """验证配置默认值"""
    # 直接实例化 Settings（不读取 .env 文件）
    s = Settings(
        DB_PASSWORD="test",
        REDIS_PASSWORD="test",
        RABBITMQ_PASSWORD="test",
        MINIO_SECRET_KEY="test",
        LLM_API_KEY="test",
        LLM_BACKUP_API_KEY="test",
        EMBEDDING_API_KEY="test",
        JWT_SECRET="test-secret-32chars-minimum!!",
        ENCRYPTION_KEY="dGVzdC1rZXktMzJieXRlcy1sb25nISEhISEh",  # dummy base64 32 bytes
        _env_file=None,
    )
    assert s.APP_NAME == "hermes"
    assert s.PORT == 8000
    assert s.DB_PORT == 5432
    assert s.ENV == "dev"
    assert s.ACCESS_TOKEN_EXPIRE_SECONDS == 28800


def test_database_url():
    """验证数据库 URL 生成"""
    s = Settings(
        DB_HOST_WRITE="localhost",
        DB_PORT=5432,
        DB_NAME="hermes",
        DB_USER="hermes",
        DB_PASSWORD="testpass",
        REDIS_PASSWORD="test",
        RABBITMQ_PASSWORD="test",
        MINIO_SECRET_KEY="test",
        LLM_API_KEY="test",
        LLM_BACKUP_API_KEY="test",
        EMBEDDING_API_KEY="test",
        JWT_SECRET="test-secret-32chars-minimum!!",
        ENCRYPTION_KEY="dGVzdC1rZXktMzJieXRlcy1sb25nISEhISEh",
        _env_file=None,
    )
    url = s.database_url
    assert "postgresql+asyncpg://" in url
    assert "hermes:testpass@localhost:5432/hermes" in url


def test_celery_broker_url():
    """验证 Celery broker URL 生成"""
    s = Settings(
        RABBITMQ_HOST="rabbitmq",
        RABBITMQ_PORT=5672,
        RABBITMQ_USER="guest",
        RABBITMQ_PASSWORD="guest",
        DB_PASSWORD="test",
        REDIS_PASSWORD="test",
        MINIO_SECRET_KEY="test",
        LLM_API_KEY="test",
        LLM_BACKUP_API_KEY="test",
        EMBEDDING_API_KEY="test",
        JWT_SECRET="test-secret-32chars-minimum!!",
        ENCRYPTION_KEY="dGVzdC1rZXktMzJieXRlcy1sb25nISEhISEh",
        _env_file=None,
    )
    url = s.celery_broker_url
    assert url == "amqp://guest:guest@rabbitmq:5672/"
