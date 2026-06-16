"""测试异常体系"""

import pytest

from hermes.core.exceptions import (
    AIServiceUnavailableError,
    AccountLockedError,
    BadRequestError,
    CaseNotFoundError,
    CaseStatusConflictError,
    ConflictError,
    CrossClientForbiddenError,
    ExternalSystemError,
    FileTooLargeError,
    ForbiddenError,
    HermesError,
    InternalError,
    KnowledgeBaseNotFoundError,
    NoPendingApprovalError,
    NotFoundError,
    RateLimitError,
    StageRetryExhaustedError,
    TokenExpiredError,
    UnauthorizedError,
    WorkflowAlreadyCompletedError,
    WorkflowAlreadyStartedError,
    WorkflowExecutionError,
    WorkflowNotStartedError,
)


class TestHermesErrorBase:
    """异常基类测试"""

    def test_basic_error(self):
        exc = HermesError(code=50000, message="错误", status_code=500)
        assert exc.code == 50000
        assert exc.message == "错误"
        assert exc.status_code == 500
        assert str(exc) == "错误"

    def test_with_detail(self):
        exc = HermesError(code=50001, message="AI 不可用", detail="timeout", status_code=500)
        d = exc.to_dict()
        assert d["code"] == 50001
        assert d["message"] == "AI 不可用"
        assert d["detail"] == "timeout"

    def test_without_detail(self):
        exc = HermesError(code=50000, message="错误", status_code=500)
        d = exc.to_dict()
        assert "detail" not in d


class TestGenericErrors:
    """通用错误类测试"""

    def test_bad_request(self):
        exc = BadRequestError()
        assert exc.code == 40000
        assert exc.status_code == 400

    def test_unauthorized(self):
        exc = UnauthorizedError(detail="Token expired")
        assert exc.code == 40100
        assert exc.status_code == 401
        assert "Token expired" in exc.to_dict()["detail"]

    def test_token_expired(self):
        exc = TokenExpiredError()
        assert exc.code == 40101

    def test_account_locked(self):
        exc = AccountLockedError()
        assert exc.code == 40102

    def test_forbidden(self):
        exc = ForbiddenError()
        assert exc.code == 40300

    def test_cross_client_forbidden(self):
        exc = CrossClientForbiddenError()
        assert exc.code == 40301

    def test_not_found(self):
        exc = NotFoundError()
        assert exc.code == 40400

    def test_conflict(self):
        exc = ConflictError()
        assert exc.code == 40900

    def test_file_too_large(self):
        exc = FileTooLargeError()
        assert exc.code == 41300

    def test_rate_limit(self):
        exc = RateLimitError()
        assert exc.code == 42900

    def test_internal_error(self):
        exc = InternalError()
        assert exc.code == 50000

    def test_ai_service_unavailable(self):
        exc = AIServiceUnavailableError()
        assert exc.code == 50001

    def test_external_system_error(self):
        exc = ExternalSystemError()
        assert exc.code == 50002


class TestCaseErrors:
    """案件模块错误测试"""

    def test_case_not_found(self):
        exc = CaseNotFoundError("c-001")
        assert exc.code == 40401
        assert exc.status_code == 404
        assert exc.message == "案件不存在"
        d = exc.to_dict()
        assert "c-001" in d["detail"]

    def test_case_status_conflict(self):
        exc = CaseStatusConflictError(detail="状态不允许")
        assert exc.code == 40901
        assert "状态不允许" in exc.to_dict()["detail"]

    def test_workflow_already_started(self):
        exc = WorkflowAlreadyStartedError()
        assert exc.code == 40902


class TestWorkflowErrors:
    """工作流错误测试"""

    def test_workflow_not_started(self):
        exc = WorkflowNotStartedError()
        assert exc.code == 40002
        assert exc.status_code == 400
        assert "工作流未启动" in exc.message

    def test_workflow_already_completed(self):
        exc = WorkflowAlreadyCompletedError()
        assert exc.code == 40003

    def test_no_pending_approval(self):
        exc = NoPendingApprovalError()
        assert exc.code == 40004
        assert "无待守门阶段" in exc.message

    def test_workflow_execution_error(self):
        exc = WorkflowExecutionError(detail="LLM 调用失败")
        assert exc.code == 42202
        assert exc.status_code == 422
        assert "LLM 调用失败" in exc.to_dict()["detail"]

    def test_stage_retry_exhausted(self):
        exc = StageRetryExhaustedError()
        assert exc.code == 42203


class TestKnowledgeErrors:
    """知识库错误测试"""

    def test_knowledge_base_not_found(self):
        exc = KnowledgeBaseNotFoundError("legal")
        assert exc.code == 40408
        assert "legal" in exc.to_dict()["detail"]
