"""
风险监控模块 — LangGraph 工作流定义

6 阶段工作流 (7×24 无人值守自动扫描):
  risk_rule → risk_scan → anomaly_filter → entity_merge → risk_classify → result_push
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class RiskMonitoringState(TypedDict, total=False):
    task_id: str
    current_stage: str
    stage_history: list[str]

    risk_rules: list[dict[str, Any]]
    anomaly_records: list[dict[str, Any]]
    merged_entities: list[dict[str, Any]]
    risk_classifications: list[dict[str, Any]]
    push_results: list[dict[str, Any]]

    pending_approval_stage: str | None
    approval_result: str | None
    error_info: dict[str, Any] | None


async def risk_rule_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.1] 风险规则清单生成"""
    logger.info("risk_rule_node_start", task_id=state.get("task_id"))
    try:
        from hermes.agents.risk_monitoring.risk_rule_agent import RiskRuleAgent
        from hermes.schemas.agents.risk_monitoring import RiskRuleAgentInput, RuleGenerationMode

        RiskRuleAgent()
        RiskRuleAgentInput(
            task_id=state.get("task_id", ""),
            mode=RuleGenerationMode.MANUAL_INPUT,
        )
        # Need db_session for KB search; skeleton mode for now
        state["risk_rules"] = []
    except Exception as e:
        logger.warning("risk_rule_agent_unavailable", error=str(e))
        state["risk_rules"] = []

    state["current_stage"] = "risk_rule"
    state["pending_approval_stage"] = "risk_rule"
    state["stage_history"] = state.get("stage_history", []) + ["risk_rule"]
    return state


async def risk_scan_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.2] 异常数据生成"""
    state["current_stage"] = "risk_scan"
    state["stage_history"] = state.get("stage_history", []) + ["risk_scan"]
    return state


async def anomaly_filter_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.2] AI初核异常"""
    state["current_stage"] = "anomaly_filter"
    state["pending_approval_stage"] = "anomaly_filter"
    state["stage_history"] = state.get("stage_history", []) + ["anomaly_filter"]
    return state


async def entity_merge_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.3] 主体合并"""
    state["current_stage"] = "entity_merge"
    state["stage_history"] = state.get("stage_history", []) + ["entity_merge"]
    return state


async def risk_classify_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.4] 风险定性"""
    state["current_stage"] = "risk_classify"
    state["pending_approval_stage"] = "risk_classify"
    state["stage_history"] = state.get("stage_history", []) + ["risk_classify"]
    return state


async def result_push_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.5] 风险结果推送"""
    state["current_stage"] = "result_push"
    state["stage_history"] = state.get("stage_history", []) + ["result_push"]
    return state


def build_risk_monitoring_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    workflow = StateGraph(RiskMonitoringState)
    workflow.add_node("risk_rule", risk_rule_node)
    workflow.add_node("risk_scan", risk_scan_node)
    workflow.add_node("anomaly_filter", anomaly_filter_node)
    workflow.add_node("entity_merge", entity_merge_node)
    workflow.add_node("risk_classify", risk_classify_node)
    workflow.add_node("result_push", result_push_node)
    workflow.set_entry_point("risk_rule")
    workflow.add_edge("risk_rule", "risk_scan")
    workflow.add_edge("risk_scan", "anomaly_filter")
    workflow.add_edge("anomaly_filter", "entity_merge")
    workflow.add_edge("entity_merge", "risk_classify")
    workflow.add_edge("risk_classify", "result_push")
    workflow.add_edge("result_push", END)
    return workflow.compile(checkpointer=checkpointer)


class RiskMonitoringWorkflowManager:
    def __init__(self):
        self._graph = build_risk_monitoring_graph()

    def start_workflow(self, task_id: str) -> str:
        thread_id = f"rm-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: RiskMonitoringState = {
            "task_id": task_id,
            "current_stage": "risk_rule",
            "stage_history": [],
            "risk_rules": [],
            "anomaly_records": [],
            "merged_entities": [],
            "risk_classifications": [],
            "push_results": [],
            "pending_approval_stage": None,
            "approval_result": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        return thread_id


risk_monitoring_graph = RiskMonitoringWorkflowManager()
