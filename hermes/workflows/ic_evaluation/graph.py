"""
内控评价模块 — LangGraph 工作流定义

13 步骤工作流 + 19 个业务循环:
  project_init → audit_plan → interview_plan → interview_questionnaire → control_matrix_update
  → design_deficiency → material_request → execution_deficiency → deficiency_confirm
  → overall_scoring → report_generation → report_review → archive
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class ICEvaluationState(TypedDict, total=False):
    task_id: str
    project_id: str
    audit_type: str
    current_stage: str
    stage_history: list[str]

    business_cycles: list[str]
    audit_plan: dict[str, Any]
    interview_plan: dict[str, Any]
    questionnaires: list[dict[str, Any]]
    design_deficiencies: list[dict[str, Any]]
    execution_deficiencies: list[dict[str, Any]]
    confirmed_deficiencies: list[dict[str, Any]]
    total_score: float
    report: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def project_init_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "project_init"
    state["stage_history"] = state.get("stage_history", []) + ["project_init"]
    return state


async def audit_plan_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "audit_plan"
    state["pending_approval_stage"] = "audit_plan"
    state["stage_history"] = state.get("stage_history", []) + ["audit_plan"]
    return state


async def interview_plan_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "interview_plan"
    state["stage_history"] = state.get("stage_history", []) + ["interview_plan"]
    return state


async def interview_questionnaire_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "interview_questionnaire"
    state["pending_approval_stage"] = "interview_questionnaire"
    state["stage_history"] = state.get("stage_history", []) + ["interview_questionnaire"]
    return state


async def design_deficiency_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "design_deficiency"
    state["pending_approval_stage"] = "design_deficiency"
    state["stage_history"] = state.get("stage_history", []) + ["design_deficiency"]
    return state


async def execution_deficiency_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "execution_deficiency"
    state["pending_approval_stage"] = "execution_deficiency"
    state["stage_history"] = state.get("stage_history", []) + ["execution_deficiency"]
    return state


async def deficiency_confirm_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "deficiency_confirm"
    state["pending_approval_stage"] = "deficiency_confirm"
    state["stage_history"] = state.get("stage_history", []) + ["deficiency_confirm"]
    return state


async def overall_scoring_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "overall_scoring"
    state["stage_history"] = state.get("stage_history", []) + ["overall_scoring"]
    return state


async def report_generation_node(state: ICEvaluationState) -> ICEvaluationState:
    state["current_stage"] = "report_generation"
    state["pending_approval_stage"] = "report_generation"
    state["stage_history"] = state.get("stage_history", []) + ["report_generation"]
    return state


def build_ic_evaluation_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(ICEvaluationState)

    workflow.add_node("project_init", project_init_node)
    workflow.add_node("audit_plan", audit_plan_node)
    workflow.add_node("interview_plan", interview_plan_node)
    workflow.add_node("interview_questionnaire", interview_questionnaire_node)
    workflow.add_node("design_deficiency", design_deficiency_node)
    workflow.add_node("execution_deficiency", execution_deficiency_node)
    workflow.add_node("deficiency_confirm", deficiency_confirm_node)
    workflow.add_node("overall_scoring", overall_scoring_node)
    workflow.add_node("report_generation", report_generation_node)

    workflow.set_entry_point("project_init")
    workflow.add_edge("project_init", "audit_plan")
    workflow.add_edge("audit_plan", "interview_plan")
    workflow.add_edge("interview_plan", "interview_questionnaire")
    workflow.add_edge("interview_questionnaire", "design_deficiency")
    workflow.add_edge("design_deficiency", "execution_deficiency")
    workflow.add_edge("execution_deficiency", "deficiency_confirm")
    workflow.add_edge("deficiency_confirm", "overall_scoring")
    workflow.add_edge("overall_scoring", "report_generation")
    workflow.add_edge("report_generation", END)

    return workflow.compile(checkpointer=checkpointer)


class ICEvaluationWorkflowManager:
    def __init__(self):
        self._graph = build_ic_evaluation_graph()

    def start_workflow(self, task_id: str, project_id: str = "") -> str:
        thread_id = f"ice-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: ICEvaluationState = {
            "task_id": task_id,
            "project_id": project_id,
            "audit_type": "ic_evaluation",
            "current_stage": "project_init",
            "stage_history": [],
            "business_cycles": [],
            "audit_plan": {},
            "interview_plan": {},
            "questionnaires": [],
            "design_deficiencies": [],
            "execution_deficiencies": [],
            "confirmed_deficiencies": [],
            "total_score": 0.0,
            "report": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


ic_evaluation_graph = ICEvaluationWorkflowManager()
