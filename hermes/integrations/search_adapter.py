"""
Search Adapter — Elasticsearch 全文检索适配器

封装 ES 索引管理、BM25 + 中文分词搜索、文档索引写入。
ES 不可用时抛出异常，调用方负责降级为 ILIKE。
"""

from __future__ import annotations

from typing import Any

from hermes.core.config import settings
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# ES 索引映射：中文分词 + 字段权重
_INDEX_MAPPING: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ik_smart_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_smart",
                    "filter": ["lowercase"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "kb_type": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "boost": 3.0,  # 标题权重最高
            },
            "content": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
                "boost": 1.0,
            },
            "content_snippet": {
                "type": "text",
                "analyzer": "ik_smart_analyzer",
            },
            "source_path": {"type": "keyword"},
            "security_level": {"type": "keyword"},
            "client": {"type": "keyword"},
            "org_id": {"type": "keyword"},
            "approval_status": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "total_chunks": {"type": "integer"},
            "updated_at": {"type": "date"},
        }
    },
}


class SearchAdapter:
    """Elasticsearch 全文检索适配器

    使用方式:
        adapter = SearchAdapter(es_client)
        results = await adapter.search(query, filters, top_k)
        await adapter.index_document(doc_dict)
    """

    def __init__(self, es_client: Any = None) -> None:
        """初始化适配器

        Args:
            es_client: AsyncElasticsearch 客户端，None 表示不可用
        """
        self._es = es_client
        self._index_name = f"{settings.ES_INDEX_PREFIX}_knowledge"
        self._initialized = False

    @property
    def available(self) -> bool:
        return self._es is not None

    async def ensure_index(self) -> None:
        """确保 ES 索引存在（不存在则创建）"""
        if not self.available or self._initialized:
            return
        try:
            exists = await self._es.indices.exists(index=self._index_name)
            if not exists:
                await self._es.indices.create(
                    index=self._index_name,
                    body=_INDEX_MAPPING,
                )
                logger.info("es_index_created", index=self._index_name)
            self._initialized = True
        except Exception as e:
            logger.warning("es_index_init_failed", error=str(e))

    async def search(
        self,
        query: str,
        kb_types: list[str],
        top_k: int,
        client_filters: list[str] | None = None,
        security_levels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """BM25 全文检索 + 中文分词

        Args:
            query: 搜索查询
            kb_types: 知识库类型过滤
            top_k: 返回数量
            client_filters: 租户过滤
            security_levels: 密级过滤

        Returns:
            [{"doc_id", "chunk_id", "kb_type", "title", "content_snippet",
              "keyword_score", "source_path", ...}, ...]
        """
        if not self.available:
            raise RuntimeError("Elasticsearch 不可用")

        await self.ensure_index()

        must_clauses: list[dict] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content", "content_snippet"],
                    "type": "best_fields",
                    "operator": "or",
                }
            },
            {"terms": {"kb_type": kb_types}},
            {"term": {"approval_status": "approved"}},
        ]

        if client_filters:
            must_clauses.append({"terms": {"client": client_filters}})
        if security_levels:
            must_clauses.append({"terms": {"security_level": security_levels}})

        try:
            response = await self._es.search(
                index=self._index_name,
                body={
                    "query": {"bool": {"must": must_clauses}},
                    "size": top_k,
                    "_source": [
                        "doc_id", "chunk_id", "kb_type", "title",
                        "content_snippet", "source_path", "chunk_index",
                        "total_chunks", "security_level", "client",
                        "org_id", "approval_status",
                    ],
                },
            )
        except Exception as e:
            logger.warning("es_search_failed", error=str(e))
            raise

        hits = response["hits"]["hits"]
        max_score = response["hits"].get("max_score") or 1.0

        results: list[dict[str, Any]] = []
        for hit in hits:
            src = hit["_source"]
            score = hit["_score"] / max_score if max_score > 0 else 0.0
            results.append({
                "doc_id": src.get("doc_id", ""),
                "chunk_id": src.get("chunk_id", ""),
                "kb_type": src.get("kb_type", ""),
                "title": src.get("title", ""),
                "content_snippet": src.get("content_snippet", ""),
                "source_path": src.get("source_path"),
                "chunk_index": src.get("chunk_index", 1),
                "total_chunks": src.get("total_chunks", 1),
                "keyword_score": round(score, 4),
                "channels": ["keyword"],
                "metadata_": {},
                "security_level": src.get("security_level", "internal"),
                "client": src.get("client", "group"),
                "org_id": src.get("org_id", "*"),
                "approval_status": src.get("approval_status", "approved"),
            })

        return results

    async def index_document(self, doc: dict[str, Any]) -> None:
        """向 ES 索引写入一条文档 chunk

        Args:
            doc: {"doc_id", "chunk_id", "kb_type", "title", "content",
                  "content_snippet", "source_path", "security_level",
                  "client", "org_id", "approval_status", "chunk_index",
                  "total_chunks", "updated_at"}
        """
        if not self.available:
            return
        await self.ensure_index()
        try:
            await self._es.index(
                index=self._index_name,
                id=doc["chunk_id"],
                body=doc,
                refresh=False,  # 异步刷新，不阻塞
            )
        except Exception as e:
            logger.warning("es_index_doc_failed", chunk_id=doc.get("chunk_id"), error=str(e))

    async def delete_document(self, chunk_id: str) -> None:
        """从 ES 索引删除一条文档"""
        if not self.available:
            return
        try:
            await self._es.delete(index=self._index_name, id=chunk_id, ignore=[404])
        except Exception as e:
            logger.warning("es_delete_doc_failed", chunk_id=chunk_id, error=str(e))

    async def delete_by_title(self, kb_type: str, title: str) -> int:
        """删除同一文档的所有 chunk（按 kb_type + title）"""
        if not self.available:
            return 0
        try:
            response = await self._es.delete_by_query(
                index=self._index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"kb_type": kb_type}},
                                {"term": {"title": title}},
                            ]
                        }
                    }
                },
            )
            deleted = response.get("deleted", 0)
            if deleted > 0:
                logger.info("es_deleted_by_title", kb_type=kb_type, title=title, count=deleted)
            return deleted
        except Exception as e:
            logger.warning("es_delete_by_title_failed", error=str(e))
            return 0
