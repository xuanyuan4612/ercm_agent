"""
离任审计模块 — LangGraph 工作流定义

6 阶段工作流:
  audit_plan → interview → material_list → issue_list → issue_confirm → exit_report
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class ExitAuditState(TypedDict, total=False):
    task_id: str
    departing_person_name: str
    departing_person_id: str
    current_stage: str
    stage_history: list[str]

    audit_plan: dict[str, Any]
    interview_questionnaires: list[dict[str, Any]]
    material_requirements: list[dict[str, Any]]
    personal_issues: list[dict[str, Any]]
    business_issues: list[dict[str, Any]]
    confirmed_issues: list[dict[str, Any]]
    exit_report: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def audit_plan_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "audit_plan"
    state["pending_approval_stage"] = "audit_plan"
    state["stage_history"] = state.get("stage_history", []) + ["audit_plan"]
    return state


async def interview_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "interview"
    state["pending_approval_stage"] = "interview"
    state["stage_history"] = state.get("stage_history", []) + ["interview"]
    return state


async def material_list_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "material_list"
    state["pending_approval_stage"] = "material_list"
    state["stage_history"] = state.get("stage_history", []) + ["material_list"]
    return state


async def issue_list_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "issue_list"
    state["pending_approval_stage"] = "issue_list"
    state["stage_history"] = state.get("stage_history", []) + ["issue_list"]
    return state


async def issue_confirm_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "issue_confirm"
    state["pending_approval_stage"] = "issue_confirm"
    state["stage_history"] = state.get("stage_history", []) + ["issue_confirm"]
    return state


async def exit_report_node(state: ExitAuditState) -> ExitAuditState:
    state["current_stage"] = "exit_report"
    state["pending_approval_stage"] = "exit_report"
    state["stage_history"] = state.get("stage_history", []) + ["exit_report"]
    return state


def build_exit_audit_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(ExitAuditState)
    workflow.add_node("audit_plan", audit_plan_node)
    workflow.add_node("interview", interview_node)
    workflow.add_node("material_list", material_list_node)
    workflow.add_node("issue_list", issue_list_node)
    workflow.add_node("issue_confirm", issue_confirm_node)
    workflow.add_node("exit_report", exit_report_node)
    workflow.set_entry_point("audit_plan")
    workflow.add_edge("audit_plan", "interview")
    workflow.add_edge("interview", "material_list")
    workflow.add_edge("material_list", "issue_list")
    workflow.add_edge("issue_list", "issue_confirm")
    workflow.add_edge("issue_confirm", "exit_report")
    workflow.add_edge("exit_report", END)
    return workflow.compile(checkpointer=checkpointer)


class ExitAuditWorkflowManager:
    def __init__(self):
        self._graph = build_exit_audit_graph()

    def start_workflow(self, task_id: str, departing_person_name: str = "", departing_person_id: str = "") -> str:
        thread_id = f"ea-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: ExitAuditState = {
            "task_id": task_id,
            "departing_person_name": departing_person_name,
            "departing_person_id": departing_person_id,
            "current_stage": "audit_plan",
            "stage_history": [],
            "audit_plan": {},
            "interview_questionnaires": [],
            "material_requirements": [],
            "personal_issues": [],
            "business_issues": [],
            "confirmed_issues": [],
            "exit_report": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


exit_audit_graph = ExitAuditWorkflowManager()
