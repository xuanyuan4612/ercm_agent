"""
商业秘密模块 — LangGraph 工作流定义

工作流:
  precheck → policy_compare → formal_review → archive
  周期任务: management_report
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class TradeSecretsState(TypedDict, total=False):
    task_id: str
    review_type: str
    current_stage: str
    stage_history: list[str]

    secrecy_info_table: dict[str, Any]
    precheck_result: dict[str, Any]
    policy_compare_result: dict[str, Any]
    formal_review_result: dict[str, Any]
    management_report: dict[str, Any]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def precheck_node(state: TradeSecretsState) -> TradeSecretsState:
    state["current_stage"] = "precheck"
    state["pending_approval_stage"] = "precheck"
    state["stage_history"] = state.get("stage_history", []) + ["precheck"]
    return state


async def policy_compare_node(state: TradeSecretsState) -> TradeSecretsState:
    state["current_stage"] = "policy_compare"
    state["stage_history"] = state.get("stage_history", []) + ["policy_compare"]
    return state


async def formal_review_node(state: TradeSecretsState) -> TradeSecretsState:
    state["current_stage"] = "formal_review"
    state["pending_approval_stage"] = "formal_review"
    state["stage_history"] = state.get("stage_history", []) + ["formal_review"]
    return state


async def management_report_node(state: TradeSecretsState) -> TradeSecretsState:
    state["current_stage"] = "management_report"
    state["pending_approval_stage"] = "management_report"
    state["stage_history"] = state.get("stage_history", []) + ["management_report"]
    return state


def build_trade_secrets_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(TradeSecretsState)
    workflow.add_node("precheck", precheck_node)
    workflow.add_node("policy_compare", policy_compare_node)
    workflow.add_node("formal_review", formal_review_node)
    workflow.add_node("management_report", management_report_node)
    workflow.set_entry_point("precheck")
    workflow.add_edge("precheck", "policy_compare")
    workflow.add_edge("policy_compare", "formal_review")
    workflow.add_edge("formal_review", END)

    # 管理报告是独立的周期入口
    # Can be invoked separately via management_report_node
    return workflow.compile(checkpointer=checkpointer)


class TradeSecretsWorkflowManager:
    def __init__(self):
        self._graph = build_trade_secrets_graph()

    def start_review_workflow(self, task_id: str) -> str:
        thread_id = f"ts-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: TradeSecretsState = {
            "task_id": task_id,
            "review_type": "pre_review",
            "current_stage": "precheck",
            "stage_history": [],
            "secrecy_info_table": {},
            "precheck_result": {},
            "policy_compare_result": {},
            "formal_review_result": {},
            "management_report": {},
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


trade_secrets_graph = TradeSecretsWorkflowManager()
