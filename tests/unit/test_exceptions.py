"""测试异常体系"""

from hermes.core.exceptions import (
    CaseNotFoundError,
    UnauthorizedError,
    WorkflowNotStartedError,
    HermesError,
)


def test_case_not_found_error():
    """验证案件不存在异常"""
    exc = CaseNotFoundError("c-001")
    assert exc.code == 40401
    assert exc.status_code == 404
    assert exc.message == "案件不存在"
    d = exc.to_dict()
    assert d["code"] == 40401
    assert "c-001" in d["detail"]


def test_unauthorized_error():
    """验证未认证异常"""
    exc = UnauthorizedError(detail="Token expired")
    assert exc.code == 40100
    assert exc.status_code == 401


def test_workflow_not_started_error():
    """验证工作流未启动异常"""
    exc = WorkflowNotStartedError()
    assert exc.code == 40002
    assert exc.status_code == 400
    assert "工作流未启动" in exc.message


def test_hermes_error_to_dict():
    """验证异常转字典"""
    exc = HermesError(code=50001, message="AI 服务不可用", detail="LLM timeout", status_code=500)
    d = exc.to_dict()
    assert d["code"] == 50001
    assert d["message"] == "AI 服务不可用"
    assert d["detail"] == "LLM timeout"
