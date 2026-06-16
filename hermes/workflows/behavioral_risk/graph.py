"""
行为风险模块 — LangGraph 工作流定义

工作流:
  data_quality → behavior_anomaly → risk_report → push
  周期任务: management_report
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class BehavioralRiskState(TypedDict, total=False):
    task_id: str
    analysis_scope: dict[str, Any]
    current_stage: str
    stage_history: list[str]

    data_quality_result: dict[str, Any]
    anomaly_result: dict[str, Any]
    risk_report: dict[str, Any]
    management_report: dict[str, Any]
    push_result: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def data_quality_node(state: BehavioralRiskState) -> BehavioralRiskState:
    state["current_stage"] = "data_quality"
    state["pending_approval_stage"] = "data_quality"
    state["stage_history"] = state.get("stage_history", []) + ["data_quality"]
    return state


async def behavior_anomaly_node(state: BehavioralRiskState) -> BehavioralRiskState:
    state["current_stage"] = "behavior_anomaly"
    state["pending_approval_stage"] = "behavior_anomaly"
    state["stage_history"] = state.get("stage_history", []) + ["behavior_anomaly"]
    return state


async def risk_report_node(state: BehavioralRiskState) -> BehavioralRiskState:
    state["current_stage"] = "risk_report"
    state["pending_approval_stage"] = "risk_report"
    state["stage_history"] = state.get("stage_history", []) + ["risk_report"]
    return state


async def management_report_node(state: BehavioralRiskState) -> BehavioralRiskState:
    state["current_stage"] = "management_report"
    state["pending_approval_stage"] = "management_report"
    state["stage_history"] = state.get("stage_history", []) + ["management_report"]
    return state


def build_behavioral_risk_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(BehavioralRiskState)
    workflow.add_node("data_quality", data_quality_node)
    workflow.add_node("behavior_anomaly", behavior_anomaly_node)
    workflow.add_node("risk_report", risk_report_node)
    workflow.add_node("management_report", management_report_node)
    workflow.set_entry_point("data_quality")
    workflow.add_edge("data_quality", "behavior_anomaly")
    workflow.add_edge("behavior_anomaly", "risk_report")
    workflow.add_edge("risk_report", END)
    return workflow.compile(checkpointer=checkpointer)


class BehavioralRiskWorkflowManager:
    def __init__(self):
        self._graph = build_behavioral_risk_graph()

    def start_analysis_workflow(self, task_id: str, analysis_scope: dict | None = None) -> str:
        thread_id = f"br-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: BehavioralRiskState = {
            "task_id": task_id,
            "analysis_scope": analysis_scope or {},
            "current_stage": "data_quality",
            "stage_history": [],
            "data_quality_result": {},
            "anomaly_result": {},
            "risk_report": {},
            "management_report": {},
            "push_result": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


behavioral_risk_graph = BehavioralRiskWorkflowManager()
