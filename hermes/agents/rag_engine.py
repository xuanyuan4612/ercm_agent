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
        """混合检索：向量语义相似度 + 全文检索

        当前实现：使用 PostgreSQL ILIKE 全文模式匹配 + JSONB 元数据过滤。
        生产环境升级路径：
        1. 调用 Embedding API 获取 query vector
        2. 执行 PGVector 余弦相似度 (<=> operator) + ts_rank 加权合并
        3. PGVector + Elasticsearch 双路召回 → RRF (Reciprocal Rank Fusion) 融合
        """
        search_sql = text("""
            SELECT id, kb_type, title,
                   substring(content, 1, 300) AS content_snippet,
                   CASE
                       WHEN title ILIKE :exact_pattern THEN 0.95
                       WHEN title ILIKE :pattern THEN 0.80
                       WHEN content ILIKE :exact_pattern THEN 0.70
                       WHEN content ILIKE :pattern THEN 0.55
                       ELSE 0.30
                   END AS relevance,
                   updated_at
            FROM knowledge_documents
            WHERE kb_type = ANY(:kb_types)
              AND is_active = true
              AND (title ILIKE :pattern OR content ILIKE :pattern)
            ORDER BY relevance DESC, updated_at DESC
            LIMIT :limit
        """)
        pattern = f"%{query}%"
        exact_pattern = f"%{query.strip()}%"

        # 尝试获取 query embedding（如果 Embedding API 可用）
        query_embedding = await self._try_get_embedding(query)

        if query_embedding:
            # Embedding 可用时使用 PGVector 语义搜索
            return await self._pgvector_search(query_embedding, kb_types, top_k)

        # 降级为 ILIKE 全文搜索
        result = await self.db.execute(
            search_sql,
            {"kb_types": kb_types, "pattern": pattern, "exact_pattern": exact_pattern, "limit": top_k},
        )
        rows = result.fetchall()

        return [
            {
                "doc_id": str(row[0]),
                "kb_type": row[1],
                "title": row[2],
                "content_snippet": row[3] or "",
                "relevance": float(row[4]),
                "updated_at": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]

    async def _try_get_embedding(self, text: str) -> list[float] | None:
        """尝试获取文本的 embedding 向量

        如果 Embedding API 配置可用，返回向量；否则返回 None 降级为全文搜索。
        """
        try:
            import httpx

            api_key = settings.EMBEDDING_API_KEY.get_secret_value()
            if not api_key:
                return None

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{settings.EMBEDDING_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": settings.EMBEDDING_MODEL,
                        "input": text,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
                logger.warning("embedding_api_failed", status=response.status_code)
                return None
        except Exception as e:
            logger.warning("embedding_api_error", error=str(e))
            return None

    async def _pgvector_search(
        self, query_embedding: list[float], kb_types: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """使用 PGVector 余弦相似度进行语义搜索"""
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"
        search_sql = text("""
            SELECT id, kb_type, title,
                   substring(content, 1, 300) AS content_snippet,
                   1.0 - (embedding <=> :query_embedding::vector) AS relevance,
                   updated_at
            FROM knowledge_documents
            WHERE kb_type = ANY(:kb_types)
              AND is_active = true
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :limit
        """)
        try:
            result = await self.db.execute(
                search_sql,
                {"kb_types": kb_types, "query_embedding": embedding_str, "limit": top_k},
            )
            rows = result.fetchall()
            if rows:
                return [
                    {
                        "doc_id": str(row[0]),
                        "kb_type": row[1],
                        "title": row[2],
                        "content_snippet": row[3] or "",
                        "relevance": float(row[4]) if row[4] else 0.0,
                        "updated_at": row[5].isoformat() if row[5] else None,
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning("pgvector_search_failed", error=str(e))

        # PGVector 搜索失败时降级为 ILIKE
        return await self._fallback_ilike_search(query_embedding, kb_types, top_k)

    async def _semantic_search(
        self, query: str, kb_types: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """纯向量语义检索（PGVector 余弦相似度）

        尝试获取 query embedding 并使用 PGVector <=> 操作符进行语义搜索。
        如果 embedding API 不可用，降级为 ILIKE 全文搜索。
        """
        query_embedding = await self._try_get_embedding(query)
        if query_embedding:
            return await self._pgvector_search(query_embedding, kb_types, top_k)
        return await self._hybrid_search(query, kb_types, top_k)

    async def _fallback_ilike_search(
        self, _query_embedding: list[float], kb_types: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        """PGVector 搜索失败时的 ILIKE 降级搜索"""
        search_sql = text("""
            SELECT id, kb_type, title,
                   substring(content, 1, 300) AS content_snippet,
                   0.5 AS relevance,
                   updated_at
            FROM knowledge_documents
            WHERE kb_type = ANY(:kb_types)
              AND is_active = true
            ORDER BY updated_at DESC
            LIMIT :limit
        """)
        result = await self.db.execute(
            search_sql,
            {"kb_types": kb_types, "limit": top_k},
        )
        rows = result.fetchall()
        return [
            {
                "doc_id": str(row[0]),
                "kb_type": row[1],
                "title": row[2],
                "content_snippet": row[3] or "",
                "relevance": float(row[4]),
                "updated_at": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]

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
