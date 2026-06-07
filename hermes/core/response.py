"""
赫尔墨斯（Hermes）统一响应模型

所有 API 返回均遵循统一的 JSON 格式：
- 成功: {"code": 0, "message": "success", "data": {...}}
- 分页: {"code": 0, "message": "success", "data": {"items": [...], "total": N, "page": 1, "page_size": 20}}
- 错误: {"code": 40401, "message": "案件不存在", "detail": "..."}
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应"""

    code: int = Field(default=0, description="响应码，0=成功，非0=错误")
    message: str = Field(default="success", description="响应消息")
    data: T | None = Field(default=None, description="响应数据")

    model_config = {"from_attributes": True}


class PaginatedData(BaseModel, Generic[T]):
    """分页数据结构"""

    items: list[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总条数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")


class ErrorResponse(BaseModel):
    """错误响应"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")
    detail: str | None = Field(default=None, description="详细信息")


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构建成功响应"""
    result: dict[str, Any] = {"code": 0, "message": message}
    if data is not None:
        result["data"] = data
    return result


def paginated(
    items: list[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """构建分页响应"""
    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
