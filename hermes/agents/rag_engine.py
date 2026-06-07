"""
RAG 检索增强生成引擎

基于 PGVector 多分区向量检索 + Elasticsearch 全文混合检索。
每个业务阶段挂载独立知识库索引。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.core.config import settings
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# 知识库类型到表分区的映射
KB_TYPE_MAP = {
    "intake": "intake",
    "investigation": "investigation",
    "analysis": "analysis",
    "disposition": "disposition",
    "enforcement": "enforcement",
    "risk_monitor": "risk_monitor",
    "ic_evaluation": "ic_evaluation",
    "special_audit": "special_audit",
    "exit_audit": "exit_audit",
    "trade_secret": "trade_secret",
    "improvement": "improvement",
    "behavior_risk": "behavior_risk",
    "common": "common",
}


class RAGEngine:
    """检索增强生成引擎

    支持两种检索模式：
    1. 混合检索 (hybrid): PGVector 语义相似度 + PostgreSQL 全文检索
       （生产环境可升级为 PGVector + Elasticsearch）
    2. 纯向量检索 (semantic): 仅 PGVector 余弦相似度
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        kb_types: list[str] | None = None,
        top_k: int = 5,
        mode: str = "hybrid",
    ) -> list[dict[str, Any]]:
        """知识库混合检索

        Args:
            query: 搜索查询文本
            kb_types: 限定知识库类型列表，None=全部
            top_k: 返回结果数
            mode: 检索模式 (hybrid/semantic)

        Returns:
            [{"doc_id", "kb_type", "title", "content_snippet", "relevance", "updated_at"}, ...]
        """
        if kb_types is None:
            kb_types = list(KB_TYPE_MAP.keys())

        valid_types = [t for t in kb_types if t in KB_TYPE_MAP]
        if not valid_types:
            return []

        if mode == "hybrid":
            return await self._hybrid_search(query, valid_types, top_k)
        return await self._semantic_search(query, valid_types, top_k)

    async def _hybrid_search(
        self, query: str, kb_types: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """混合检索：向量相似度 + 全文检索"""
        # TODO: 实际实现需调用 Embedding API 获取 query vector，
        # 然后执行 PGVector 余弦相似度 + ts_rank 加权合并
        # 生产环境：PGVector + Elasticsearch 双路召回 → RRF 融合

        # 当前骨架：使用 ILIKE 进行近似搜索
        search_sql = text("""
            SELECT id, kb_type, title,
                   substring(content, 1, 300) AS content_snippet,
                   0.8 AS relevance,
                   updated_at
            FROM knowledge_documents
            WHERE kb_type = ANY(:kb_types)
              AND is_active = true
              AND (title ILIKE :pattern OR content ILIKE :pattern)
            ORDER BY updated_at DESC
            LIMIT :limit
        """)
        pattern = f"%{query}%"
        result = await self.db.execute(
            search_sql,
            {"kb_types": kb_types, "pattern": pattern, "limit": top_k},
        )
        rows = result.fetchall()

        return [
            {
                "doc_id": str(row[0]),
                "kb_type": row[1],
                "title": row[2],
                "content_snippet": row[3] or "",
                "relevance": row[4],
                "updated_at": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]

    async def _semantic_search(
        self, query: str, kb_types: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """纯向量语义检索（PGVector 余弦相似度）"""
        # TODO: 调用 Embedding API 获取 query vector，
        # 通过 PGVector 的 <=> 运算符进行余弦相似度搜索
        return await self._hybrid_search(query, kb_types, top_k)

    async def get_retrieval_context(
        self,
        query: str,
        kb_types: list[str],
        top_k: int = 5,
    ) -> str:
        """获取格式化后的检索上下文（用于注入 LLM Prompt）

        Returns:
            格式化的上下文字符串，可直接拼接至 Prompt
        """
        results = await self.search(query, kb_types, top_k)
        if not results:
            return "（未找到相关知识库内容）"

        lines = ["【相关知识库内容】"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n--- 参考 {i} (类型: {r['kb_type']}, 相关度: {r['relevance']:.2f}) ---")
            lines.append(f"标题: {r['title']}")
            lines.append(f"内容: {r['content_snippet']}")
        return "\n".join(lines)
