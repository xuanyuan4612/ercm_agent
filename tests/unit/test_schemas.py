"""测试 Pydantic schemas"""

import pytest
from pydantic import ValidationError

from hermes.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    UserInfo,
)
from hermes.schemas.case import (
    CaseBrief,
    CaseCreateRequest,
    CaseQueryParams,
    CaseUpdateRequest,
)
from hermes.schemas.workflow import (
    ApprovalHistoryEntry,
    ApprovalSubmitRequest,
    PendingApprovalResponse,
    RegenerateRequest,
    WorkflowStartResponse,
    WorkflowStatusResponse,
)

# ── 认证 Schemas ──────────────────────────────────────────────────

class TestLoginRequest:
    def test_valid(self):
        req = LoginRequest(username="testuser", password="secret123")
        assert req.username == "testuser"
        assert req.password == "secret123"

    def test_username_too_short(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="a", password="secret")

    def test_username_too_long(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="a" * 51, password="secret")

    def test_empty_password_rejected(self):
        """密码最小长度为 1"""
        with pytest.raises(ValidationError):
            LoginRequest(username="testuser", password="")


class TestUserInfo:
    def test_valid(self):
        info = UserInfo(id="1", username="admin", role="group", display_name="管理员")
        assert info.id == "1"
        assert info.role == "group"

    def test_display_name_optional(self):
        info = UserInfo(id="1", username="admin", role="ecovacs")
        assert info.display_name is None


class TestLoginResponse:
    def test_valid(self):
        resp = LoginResponse(
            access_token="at",
            refresh_token="rt",
            token_type="bearer",
            expires_in=28800,
            user_info=UserInfo(id="1", username="admin", role="group"),
        )
        assert resp.access_token == "at"
        assert resp.user_info.username == "admin"


class TestRefreshRequest:
    def test_valid(self):
        req = RefreshRequest(refresh_token="some-refresh-token")
        assert req.refresh_token == "some-refresh-token"


class TestRefreshResponse:
    def test_valid(self):
        resp = RefreshResponse(access_token="new-at", expires_in=28800)
        assert resp.access_token == "new-at"


# ── 案件 Schemas ──────────────────────────────────────────────────

class TestCaseCreateRequest:
    def test_minimal(self):
        req = CaseCreateRequest(fraud_source="manual", client="ecovacs")
        assert req.fraud_source == "manual"
        assert req.client == "ecovacs"
        assert req.reported_staff_names == []

    def test_full(self):
        req = CaseCreateRequest(
            fraud_source="phone",
            client="tineco",
            reported_staff_names=["张三"],
            reported_supplier_names=["供应商A"],
            fraud_event_detail="事件详情",
            proof="证据",
            attachments=["/file/1.pdf"],
            fraud_tel="13812345678",
            fraud_email="test@test.com",
            risk_control_case_id="RC-001",
        )
        assert len(req.reported_staff_names) == 1
        assert req.fraud_tel == "13812345678"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CaseCreateRequest(fraud_source="manual")  # 缺少 client


class TestCaseUpdateRequest:
    def test_all_fields_optional(self):
        req = CaseUpdateRequest()
        assert req.fraud_event_detail is None
        assert req.proof is None

    def test_partial_update(self):
        req = CaseUpdateRequest(fraud_event_detail="new detail")
        assert req.fraud_event_detail == "new detail"
        assert req.proof is None


class TestCaseQueryParams:
    def test_defaults(self):
        params = CaseQueryParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.client is None

    def test_custom(self):
        params = CaseQueryParams(page=2, page_size=10, client="ecovacs")
        assert params.page == 2
        assert params.page_size == 10
        assert params.client == "ecovacs"

    def test_page_min(self):
        with pytest.raises(ValidationError):
            CaseQueryParams(page=0)


class TestCaseBrief:
    def test_valid(self):
        brief = CaseBrief(
            id="uuid-1",
            task_id="SD20260615001",
            client="ecovacs",
            fraud_source="manual",
            status="pending",
        )
        assert brief.id == "uuid-1"
        assert brief.case_code is None


# ── 工作流 Schemas ────────────────────────────────────────────────

class TestWorkflowStartResponse:
    def test_valid(self):
        resp = WorkflowStartResponse(
            thread_id="thread-1", current_stage="intake", status="investigating"
        )
        assert resp.thread_id == "thread-1"
        assert resp.current_stage == "intake"


class TestWorkflowStatusResponse:
    def test_defaults(self):
        resp = WorkflowStatusResponse()
        assert resp.current_stage is None
        assert resp.stage_history == []
        assert not resp.needs_human_intervention

    def test_active_workflow(self):
        resp = WorkflowStatusResponse(
            current_stage="intake",
            stage_history=["intake"],
            pending_approval_stage="intake",
            needs_human_intervention=True,
        )
        assert resp.needs_human_intervention


class TestApprovalSubmitRequest:
    def test_valid(self):
        req = ApprovalSubmitRequest(action="approved", comment="同意")
        assert req.action == "approved"
        assert req.comment == "同意"
        assert req.modifications == {}

    def test_missing_action(self):
        with pytest.raises(ValidationError):
            ApprovalSubmitRequest()


class TestRegenerateRequest:
    def test_valid(self):
        req = RegenerateRequest(selected_text="原文", instruction="改写")
        assert req.selected_text == "原文"
        assert req.instruction == "改写"

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            RegenerateRequest(selected_text="原文")


class TestApprovalHistoryEntry:
    def test_valid(self):
        entry = ApprovalHistoryEntry(
            id="uuid-1",
            stage_name="intake",
            reviewer_id="admin",
            action="approved",
        )
        assert entry.stage_name == "intake"
        assert entry.comment is None


class TestPendingApprovalResponse:
    def test_valid(self):
        resp = PendingApprovalResponse(
            stage="intake",
            ai_output={"result": "pass"},
        )
        assert resp.stage == "intake"
        assert resp.ai_output == {"result": "pass"}
        assert resp.knowledge_refs == []
