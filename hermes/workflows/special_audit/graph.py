"""
专项审计模块 — LangGraph 工作流定义

5 阶段工作流:
  audit_plan → interview → audit_check → issue_confirm → audit_report
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class SpecialAuditState(TypedDict, total=False):
    task_id: str
    audit_objective: str
    current_stage: str
    stage_history: list[str]

    audit_plan: dict[str, Any]
    interview_questionnaires: list[dict[str, Any]]
    audit_findings: list[dict[str, Any]]
    confirmed_issues: list[dict[str, Any]]
    audit_report: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def audit_plan_node(state: SpecialAuditState) -> SpecialAuditState:
    state["current_stage"] = "audit_plan"
    state["pending_approval_stage"] = "audit_plan"
    state["stage_history"] = state.get("stage_history", []) + ["audit_plan"]
    return state


async def interview_node(state: SpecialAuditState) -> SpecialAuditState:
    state["current_stage"] = "interview"
    state["pending_approval_stage"] = "interview"
    state["stage_history"] = state.get("stage_history", []) + ["interview"]
    return state


async def audit_check_node(state: SpecialAuditState) -> SpecialAuditState:
    state["current_stage"] = "audit_check"
    state["pending_approval_stage"] = "audit_check"
    state["stage_history"] = state.get("stage_history", []) + ["audit_check"]
    return state


async def issue_confirm_node(state: SpecialAuditState) -> SpecialAuditState:
    state["current_stage"] = "issue_confirm"
    state["pending_approval_stage"] = "issue_confirm"
    state["stage_history"] = state.get("stage_history", []) + ["issue_confirm"]
    return state


async def audit_report_node(state: SpecialAuditState) -> SpecialAuditState:
    state["current_stage"] = "audit_report"
    state["pending_approval_stage"] = "audit_report"
    state["stage_history"] = state.get("stage_history", []) + ["audit_report"]
    return state


def build_special_audit_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(SpecialAuditState)
    workflow.add_node("audit_plan", audit_plan_node)
    workflow.add_node("interview", interview_node)
    workflow.add_node("audit_check", audit_check_node)
    workflow.add_node("issue_confirm", issue_confirm_node)
    workflow.add_node("audit_report", audit_report_node)
    workflow.set_entry_point("audit_plan")
    workflow.add_edge("audit_plan", "interview")
    workflow.add_edge("interview", "audit_check")
    workflow.add_edge("audit_check", "issue_confirm")
    workflow.add_edge("issue_confirm", "audit_report")
    workflow.add_edge("audit_report", END)
    return workflow.compile(checkpointer=checkpointer)


class SpecialAuditWorkflowManager:
    def __init__(self):
        self._graph = build_special_audit_graph()

    def start_workflow(self, task_id: str, audit_objective: str = "") -> str:
        thread_id = f"sa-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: SpecialAuditState = {
            "task_id": task_id,
            "audit_objective": audit_objective,
            "current_stage": "audit_plan",
            "stage_history": [],
            "audit_plan": {},
            "interview_questionnaires": [],
            "audit_findings": [],
            "confirmed_issues": [],
            "audit_report": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


special_audit_graph = SpecialAuditWorkflowManager()
