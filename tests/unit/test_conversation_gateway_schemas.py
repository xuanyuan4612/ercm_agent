"""Test conversation gateway Pydantic schemas"""
import pytest
from pydantic import ValidationError

from hermes.schemas.agents.conversation_gateway import (
    AttachmentRef,
    GatewayAgentInput,
    GatewayAgentOutput,
    IntentResult,
    IntentType,
    OperationType,
    PageContext,
    ProposedAction,
    RouteDecisionType,
    SafetyResult,
    UserPermissions,
)


class TestPageContext:
    def test_default_values(self):
        ctx = PageContext()
        assert ctx.route is None
        assert ctx.case_id is None
        assert ctx.module is None
        assert ctx.stage is None

    def test_full_context(self):
        ctx = PageContext(
            route="/cases/create",
            case_id="CASE-001",
            module="integrity_supervision",
            stage="intake",
        )
        assert ctx.route == "/cases/create"
        assert ctx.module == "integrity_supervision"


class TestGatewayAgentInput:
    def test_minimal_input(self):
        inp = GatewayAgentInput(
            session_id="sess-001",
            user_id="user-001",
            message="帮我创建案件",
        )
        assert inp.session_id == "sess-001"
        assert inp.message == "帮我创建案件"
        assert inp.page_context.route is None
        assert inp.user_permissions.role == "viewer"

    def test_with_page_context_and_attachments(self):
        inp = GatewayAgentInput(
            session_id="sess-001",
            user_id="user-001",
            message="建一个线索",
            page_context=PageContext(route="/cases/create", module="integrity_supervision"),
            attachment_refs=[
                AttachmentRef(file_id="f1", file_name="举报.pdf", parsed_status="completed")
            ],
            user_permissions=UserPermissions(
                role="ecovacs",
                client_scope=["ecovacs"],
                allowed_modules=["integrity_supervision", "risk_monitoring"],
            ),
        )
        assert len(inp.attachment_refs) == 1
        assert inp.attachment_refs[0].file_name == "举报.pdf"
        assert inp.user_permissions.client_scope == ["ecovacs"]
        assert inp.user_permissions.allowed_modules == ["integrity_supervision", "risk_monitoring"]


class TestGatewayAgentOutput:
    def test_default_output(self):
        out = GatewayAgentOutput(reply="你好")
        assert out.reply == "你好"
        assert out.intent.intent_type == IntentType.UNSUPPORTED
        assert out.safety.permission_result == "allowed"
        assert out.safety.prompt_injection_detected is False

    def test_full_output(self):
        out = GatewayAgentOutput(
            reply="我将帮你创建廉洁监察线索。",
            intent=IntentResult(
                intent_type=IntentType.OPERATION,
                operation=OperationType.CREATE_CASE,
                module="integrity_supervision",
                confidence=0.92,
            ),
            slots={"client": "ecovacs", "fraud_source": "manual"},
            missing_fields=["fraud_event_detail"],
            proposed_action=ProposedAction(
                type=RouteDecisionType.PREVIEW_ACTION,
                operation=OperationType.CREATE_CASE,
                requires_user_confirmation=True,
            ),
            safety=SafetyResult(permission_result="allowed"),
        )
        assert out.intent.operation == OperationType.CREATE_CASE
        assert out.intent.confidence == 0.92
        assert "fraud_event_detail" in out.missing_fields
        assert out.proposed_action.requires_user_confirmation is True


class TestIntentResult:
    def test_defaults(self):
        ir = IntentResult()
        assert ir.intent_type == IntentType.UNSUPPORTED
        assert ir.confidence == 0.0

    def test_serialize_operation_intent(self):
        ir = IntentResult(
            intent_type=IntentType.OPERATION,
            operation=OperationType.CREATE_CASE,
            module="integrity_supervision",
            confidence=0.91,
        )
        d = ir.model_dump()
        assert d["intent_type"] == "operation_intent"
        assert d["operation"] == "create_case"


class TestSafetyResult:
    def test_denied_result(self):
        safety = SafetyResult(
            permission_result="denied",
            denied_reason="cross_module_forbidden",
        )
        assert safety.permission_result == "denied"
        assert safety.denied_reason == "cross_module_forbidden"
        assert safety.prompt_injection_detected is False

    def test_injection_detected(self):
        safety = SafetyResult(
            permission_result="denied",
            prompt_injection_detected=True,
            denied_reason="prompt_injection_detected",
        )
        assert safety.prompt_injection_detected is True
