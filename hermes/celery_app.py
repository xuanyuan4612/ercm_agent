"""
Celery 异步任务配置

基于 RabbitMQ 消息队列，9 个业务队列 + DLX 死信队列。

Worker 启动方式：
    celery -A hermes.celery_app worker -Q audio -n audio-worker@%h --concurrency=2
    celery -A hermes.celery_app worker -Q llm,default -n llm-worker@%h --concurrency=5
"""

from __future__ import annotations

from celery import Celery

from hermes.core.config import settings

# 队列定义
TASK_QUEUES = {
    "audio": {"queue": "hermes.audio", "routing_key": "audio"},
    "image": {"queue": "hermes.image", "routing_key": "image"},
    "video": {"queue": "hermes.video", "routing_key": "video"},
    "doc": {"queue": "hermes.doc", "routing_key": "doc"},
    "report": {"queue": "hermes.report", "routing_key": "report"},
    "sync": {"queue": "hermes.sync", "routing_key": "sync"},
    "a2a": {"queue": "hermes.a2a", "routing_key": "a2a"},
    "llm": {"queue": "hermes.llm", "routing_key": "llm"},
    "kb": {"queue": "hermes.kb", "routing_key": "kb"},
}

app = Celery(
    "hermes",
    broker=settings.celery_broker_url,
    backend=None,  # 不需要结果后端
    include=["hermes.tasks"],
)

# Celery 配置
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,  # 任务完成后才 ACK
    task_reject_on_worker_lost=True,
    task_default_queue="hermes.default",
    task_default_routing_key="default",
    task_queues=[
        {"name": "hermes.default", "routing_key": "default"},
        {"name": "hermes.audio", "routing_key": "audio"},
        {"name": "hermes.image", "routing_key": "image"},
        {"name": "hermes.video", "routing_key": "video"},
        {"name": "hermes.doc", "routing_key": "doc"},
        {"name": "hermes.report", "routing_key": "report"},
        {"name": "hermes.sync", "routing_key": "sync"},
        {"name": "hermes.a2a", "routing_key": "a2a"},
        {"name": "hermes.llm", "routing_key": "llm"},
        {"name": "hermes.kb", "routing_key": "kb"},
    ],
    task_routes={
        "hermes.tasks.audio.*": {"queue": "hermes.audio"},
        "hermes.tasks.image.*": {"queue": "hermes.image"},
        "hermes.tasks.video.*": {"queue": "hermes.video"},
        "hermes.tasks.doc.*": {"queue": "hermes.doc"},
        "hermes.tasks.report.*": {"queue": "hermes.report"},
        "hermes.tasks.sync.*": {"queue": "hermes.sync"},
        "hermes.tasks.a2a.*": {"queue": "hermes.a2a"},
        "hermes.tasks.llm.*": {"queue": "hermes.llm"},
        "hermes.tasks.kb.*": {"queue": "hermes.kb"},
    },
    broker_transport_options={
        "confirm_publish": True,  # Publisher Confirm
        "max_retries": 3,
    },
    task_annotations={
        "*": {
            "max_retries": 3,
            "default_retry_delay": 10,  # seconds
            "acks_late": True,
        },
    },
)
