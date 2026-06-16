"""
持续改善模块 — LangGraph 工作流定义

状态流转: 问题待推送 → 计划待提交 → 计划待审批 → 整改答复待提交 → 已整改待复核 → 整改完成

工作流:
  issue_ingest → plan_dispatch → plan_review → evidence_review → closure_acceptance → knowledge_precipitation → archive
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class ContinuousImprovementState(TypedDict, total=False):
    task_id: str
    issue_source: str
    current_stage: str
    issue_status: str  # 见 IssueStatus 枚举
    stage_history: list[str]

    issues: list[dict[str, Any]]
    ingest_result: dict[str, Any]
    plan_review_result: dict[str, Any]
    evidence_review_result: dict[str, Any]
    reminder_result: dict[str, Any]
    closure_result: dict[str, Any]
    knowledge_result: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    review_count: int  # 退回次数
    error_info: dict[str, Any] | None


async def issue_ingest_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "issue_ingest"
    state["pending_approval_stage"] = "issue_ingest"
    state["issue_status"] = "问题待推送"
    state["stage_history"] = state.get("stage_history", []) + ["issue_ingest"]
    return state


async def plan_dispatch_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "plan_dispatch"
    state["issue_status"] = "计划待提交"
    state["stage_history"] = state.get("stage_history", []) + ["plan_dispatch"]
    return state


async def plan_review_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "plan_review"
    state["pending_approval_stage"] = "plan_review"
    state["issue_status"] = "计划待审批"
    state["stage_history"] = state.get("stage_history", []) + ["plan_review"]
    return state


async def evidence_review_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "evidence_review"
    state["pending_approval_stage"] = "evidence_review"
    state["issue_status"] = "已整改待复核"
    state["stage_history"] = state.get("stage_history", []) + ["evidence_review"]
    return state


async def closure_acceptance_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "closure_acceptance"
    state["pending_approval_stage"] = "closure_acceptance"
    state["stage_history"] = state.get("stage_history", []) + ["closure_acceptance"]
    return state


async def knowledge_precipitation_node(state: ContinuousImprovementState) -> ContinuousImprovementState:
    state["current_stage"] = "knowledge_precipitation"
    state["pending_approval_stage"] = "knowledge_precipitation"
    state["issue_status"] = "整改完成"
    state["stage_history"] = state.get("stage_history", []) + ["knowledge_precipitation"]
    return state


def route_after_plan_review(state: ContinuousImprovementState) -> Literal["plan_dispatch", "evidence_review"]:
    """计划审核通过→进入证据复核；退回→返回计划修改"""
    if state.get("approval_result") == "rejected":
        return "plan_dispatch"
    return "evidence_review"


def route_after_evidence_review(state: ContinuousImprovementState) -> Literal["plan_dispatch", "closure_acceptance"]:
    """证据复核通过→关闭验收；退回→返回整改"""
    if state.get("approval_result") == "rejected":
        state["review_count"] = state.get("review_count", 0) + 1
        return "plan_dispatch"
    return "closure_acceptance"


def build_continuous_improvement_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(ContinuousImprovementState)
    workflow.add_node("issue_ingest", issue_ingest_node)
    workflow.add_node("plan_dispatch", plan_dispatch_node)
    workflow.add_node("plan_review", plan_review_node)
    workflow.add_node("evidence_review", evidence_review_node)
    workflow.add_node("closure_acceptance", closure_acceptance_node)
    workflow.add_node("knowledge_precipitation", knowledge_precipitation_node)

    workflow.set_entry_point("issue_ingest")
    workflow.add_edge("issue_ingest", "plan_dispatch")
    workflow.add_edge("plan_dispatch", "plan_review")
    workflow.add_conditional_edges("plan_review", route_after_plan_review)
    workflow.add_conditional_edges("evidence_review", route_after_evidence_review)
    workflow.add_edge("closure_acceptance", "knowledge_precipitation")
    workflow.add_edge("knowledge_precipitation", END)

    return workflow.compile(checkpointer=checkpointer)


class ContinuousImprovementWorkflowManager:
    def __init__(self):
        self._graph = build_continuous_improvement_graph()

    def start_workflow(self, task_id: str, issue_source: str = "") -> str:
        thread_id = f"ci-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: ContinuousImprovementState = {
            "task_id": task_id,
            "issue_source": issue_source,
            "current_stage": "issue_ingest",
            "issue_status": "问题待推送",
            "stage_history": [],
            "issues": [],
            "ingest_result": {},
            "plan_review_result": {},
            "evidence_review_result": {},
            "reminder_result": {},
            "closure_result": {},
            "knowledge_result": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "review_count": 0,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


continuous_improvement_graph = ContinuousImprovementWorkflowManager()
