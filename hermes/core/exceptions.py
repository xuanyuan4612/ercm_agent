"""
赫尔墨斯（Hermes）统一异常体系

按"HTTP状态码前三位 + 模块编号 + 错误序号"的5位错误码格式。
"""

from __future__ import annotations

from typing import Any


class HermesError(Exception):
    """赫尔墨斯异常基类。

    Attributes:
        code: 5位错误码
        message: 中文错误描述
        detail: 详细错误信息（可选）
        status_code: HTTP 状态码
    """

    def __init__(
        self,
        code: int,
        message: str,
        detail: str | None = None,
        status_code: int = 500,
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            result["detail"] = self.detail
        return result


# ── 通用错误 (00) ──────────────────────────────────────────────

class BadRequestError(HermesError):
    def __init__(self, message: str = "请求参数错误", detail: str | None = None, code: int = 40000):
        super().__init__(code=code, message=message, detail=detail, status_code=400)


class UnauthorizedError(HermesError):
    def __init__(self, message: str = "未认证", detail: str | None = None):
        super().__init__(code=40100, message=message, detail=detail, status_code=401)


class TokenExpiredError(HermesError):
    def __init__(self, message: str = "令牌已过期", detail: str | None = None):
        super().__init__(code=40101, message=message, detail=detail, status_code=401)


class AccountLockedError(HermesError):
    def __init__(self, message: str = "账号已锁定", detail: str | None = None):
        super().__init__(code=40102, message=message, detail=detail, status_code=401)


class ForbiddenError(HermesError):
    def __init__(self, message: str = "无权限访问", detail: str | None = None):
        super().__init__(code=40300, message=message, detail=detail, status_code=403)


class CrossClientForbiddenError(HermesError):
    def __init__(self, message: str = "跨事业部数据不可见", detail: str | None = None):
        super().__init__(code=40301, message=message, detail=detail, status_code=403)


class NotFoundError(HermesError):
    def __init__(self, message: str = "资源不存在", detail: str | None = None, code: int = 40400):
        super().__init__(code=code, message=message, detail=detail, status_code=404)


class ConflictError(HermesError):
    def __init__(self, message: str = "资源冲突", detail: str | None = None, code: int = 40900):
        super().__init__(code=code, message=message, detail=detail, status_code=409)


class FileTooLargeError(HermesError):
    def __init__(self, message: str = "文件大小超限", detail: str | None = None):
        super().__init__(code=41300, message=message, detail=detail, status_code=413)


class RateLimitError(HermesError):
    def __init__(self, message: str = "请求频率超限", detail: str | None = None):
        super().__init__(code=42900, message=message, detail=detail, status_code=429)


class InternalError(HermesError):
    def __init__(self, message: str = "服务器内部错误", detail: str | None = None):
        super().__init__(code=50000, message=message, detail=detail, status_code=500)


class AIServiceUnavailableError(HermesError):
    def __init__(self, message: str = "AI 服务不可用", detail: str | None = None):
        super().__init__(code=50001, message=message, detail=detail, status_code=500)


class ExternalSystemError(HermesError):
    def __init__(self, message: str = "外部系统不可用", detail: str | None = None):
        super().__init__(code=50002, message=message, detail=detail, status_code=500)


# ── 案件模块错误 (01) ─────────────────────────────────────────

class CaseNotFoundError(NotFoundError):
    def __init__(self, case_id: str):
        super().__init__(
            code=40401,
            message="案件不存在",
            detail=f"case_id={case_id} not found",
        )


class CaseStatusConflictError(ConflictError):
    def __init__(self, message: str = "案件状态不允许操作", detail: str | None = None):
        super().__init__(code=40901, message=message, detail=detail)


class WorkflowAlreadyStartedError(ConflictError):
    def __init__(self, message: str = "工作流已启动", detail: str | None = None):
        super().__init__(code=40902, message=message, detail=detail)


# ── 工作流错误 (02) ───────────────────────────────────────────

class WorkflowNotStartedError(BadRequestError):
    def __init__(self):
        super().__init__(code=40002, message="工作流未启动", detail="请先调用 start 接口")


class WorkflowAlreadyCompletedError(BadRequestError):
    def __init__(self):
        super().__init__(code=40003, message="工作流已完成", detail="工作流已结束，无法恢复")


class NoPendingApprovalError(BadRequestError):
    def __init__(self):
        super().__init__(code=40004, message="无待守门阶段", detail="当前没有等待守门的阶段")


class WorkflowExecutionError(HermesError):
    def __init__(self, message: str = "工作流执行失败", detail: str | None = None):
        super().__init__(code=42202, message=message, detail=detail, status_code=422)


class StageRetryExhaustedError(HermesError):
    def __init__(self, message: str = "阶段重试次数超限", detail: str | None = None):
        super().__init__(code=42203, message=message, detail=detail, status_code=422)


# ── 知识库错误 (08) ───────────────────────────────────────────

class KnowledgeBaseNotFoundError(NotFoundError):
    def __init__(self, kb_type: str):
        super().__init__(
            code=40408,
            message="知识库类型不存在",
            detail=f"kb_type={kb_type} not found",
        )
