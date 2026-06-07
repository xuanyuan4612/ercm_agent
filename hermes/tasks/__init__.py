"""Celery 异步任务定义

按队列分模块：
- audio: 音频处理 (Whisper ASR + 说话人分离)
- image: 图像处理 (PaddleOCR + CLIP 分类)
- video: 视频处理 (OpenCV 关键帧 + 场景分析)
- doc: 文档处理 (unstructured.io 解析 + Chunking + Embedding)
- report: 报告生成 (python-docx / openpyxl)
- sync: 外部系统同步
- a2a: A2A 智能体通信
- llm: LLM 推理任务
- kb: 知识库索引任务
"""

from hermes.celery_app import app


@app.task(name="hermes.tasks.noop", bind=True, queue="hermes.default")
def noop(self):
    """占位任务，用于测试 Celery 连接"""
    return {"status": "ok"}
