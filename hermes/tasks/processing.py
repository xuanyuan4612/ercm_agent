"""Celery 异步处理任务

按队列分：
- audio: 音频处理 (Whisper ASR)
- image: 图像处理 (PaddleOCR)
- video: 视频处理 (OpenCV 关键帧)
- doc: 文档处理 (unstructured.io 解析 → Chunking → Embedding)
- report: 文档生成 (python-docx / openpyxl)
- llm: LLM 推理任务
"""

from hermes.celery_app import app


# ── 音频处理 (hermes.audio) ───────────────────────────────────

@app.task(name="hermes.tasks.audio.transcribe", bind=True, queue="hermes.audio", max_retries=3)
def transcribe_audio(self, file_path: str, language: str = "auto"):
    """Whisper ASR 语音转文字"""
    # TODO: 加载 Whisper 模型，转录音频
    return {"task_id": self.request.id, "status": "queued", "file": file_path}


@app.task(name="hermes.tasks.audio.diarize", bind=True, queue="hermes.audio", max_retries=2)
def diarize_speakers(self, file_path: str):
    """说话人分离"""
    return {"task_id": self.request.id, "status": "queued", "file": file_path}


# ── 图像处理 (hermes.image) ──────────────────────────────────

@app.task(name="hermes.tasks.image.ocr", bind=True, queue="hermes.image", max_retries=2)
def ocr_image(self, file_path: str):
    """PaddleOCR 文字提取"""
    return {"task_id": self.request.id, "status": "queued", "file": file_path}


@app.task(name="hermes.tasks.image.classify", bind=True, queue="hermes.image", max_retries=2)
def classify_image(self, file_path: str):
    """CLIP 图像分类"""
    return {"task_id": self.request.id, "status": "queued", "file": file_path}


# ── 文档处理 (hermes.doc) ────────────────────────────────────

@app.task(name="hermes.tasks.doc.parse", bind=True, queue="hermes.doc", max_retries=2)
def parse_document(self, file_path: str, file_type: str = "pdf"):
    """unstructured.io 文档解析"""
    return {"task_id": self.request.id, "status": "queued", "file": file_path}


@app.task(name="hermes.tasks.doc.chunk_and_embed", bind=True, queue="hermes.doc", max_retries=2)
def chunk_and_embed(self, doc_id: str, kb_type: str):
    """智能分块 + Embedding + PGVector 索引"""
    return {"task_id": self.request.id, "status": "queued", "doc_id": doc_id}


# ── 报告生成 (hermes.report) ──────────────────────────────────

@app.task(name="hermes.tasks.report.generate_docx", bind=True, queue="hermes.report", max_retries=2)
def generate_docx(self, template: str, data: dict, output_path: str):
    """Word 报告生成"""
    return {"task_id": self.request.id, "status": "queued"}


@app.task(name="hermes.tasks.report.generate_xlsx", bind=True, queue="hermes.report", max_retries=2)
def generate_xlsx(self, template: str, data: list[dict], output_path: str):
    """Excel 报表生成"""
    return {"task_id": self.request.id, "status": "queued"}


# ── LLM 推理 (hermes.llm) ────────────────────────────────────

@app.task(name="hermes.tasks.llm.invoke", bind=True, queue="hermes.llm", max_retries=2)
def llm_invoke(self, messages: list[dict], agent_type: str = "default"):
    """LLM 推理任务（异步执行）"""
    # TODO: 调用 LLM Adapter 执行推理
    return {"task_id": self.request.id, "status": "queued", "agent_type": agent_type}
