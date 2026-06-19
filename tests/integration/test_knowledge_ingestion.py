"""知识入库集成测试"""
import pytest
from sqlalchemy import select

from hermes.db.models.knowledge import KnowledgeDocument
from hermes.services.knowledge_ingestion import KnowledgeIngestionService


@pytest.mark.asyncio
async def test_ingest_text_creates_document(db_session):
    """纯文本入库应成功创建文档"""
    service = KnowledgeIngestionService(db_session)
    result = await service.ingest_text(
        title="测试制度文档",
        content="这是一份关于供应商管理的测试制度文件，包含详细的供应商准入标准和评估流程。",
        kb_type="common",
        client="group",
        security_level="public",
    )
    await db_session.commit()

    assert result.success is True
    assert result.chunks_created >= 1
    assert result.doc_id != ""

    # 验证数据库中的记录
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.title == "测试制度文档")
    db_result = await db_session.execute(stmt)
    doc = db_result.scalar_one_or_none()
    assert doc is not None
    assert doc.kb_type == "common"
    assert doc.security_level == "public"


@pytest.mark.asyncio
async def test_clean_text_removes_noise():
    """文本清洗应去除多余空白和控制字符"""
    service = KnowledgeIngestionService(None)  # type: ignore[arg-type]
    dirty = "第一段  \n\n\n\n第二段\x00测试"
    clean = service._clean_text(dirty)
    assert "\x00" not in clean
    assert "\n\n\n\n" not in clean


@pytest.mark.asyncio
async def test_chunk_text_splits_long_content():
    """长文本应被正确分块"""
    from hermes.core.config import settings
    service = KnowledgeIngestionService(None)  # type: ignore[arg-type]
    long_text = "这是一个测试。" * 300  # ~3000 字符
    chunks = service._chunk_text(long_text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= settings.INGESTION_CHUNK_SIZE + settings.INGESTION_CHUNK_OVERLAP + 100


@pytest.mark.asyncio
async def test_unsupported_format():
    """不支持的文件格式应报错"""
    service = KnowledgeIngestionService(None)  # type: ignore[arg-type]
    result = await service.ingest_file(
        file_content=b"test",
        filename="test.xyz",
        kb_type="common",
    )
    assert result.success is False
    assert "不支持" in result.error
