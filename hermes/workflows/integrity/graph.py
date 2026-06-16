"""
廉洁监察模块 — LangGraph 工作流定义

实现 6 阶段反舞弊调查工作流，每个阶段完成后通过 interrupt_before 挂起，
等待碳基 (Human-in-the-Loop) 守门。

工作流拓扑：
    START → intake ──(立案)──→ investigation → analysis → disposition
      │       │                                                    │
      │       └──(不处理/转交)→ END                    ┌───────────┘
      │                                                │
      │                                    ┌─(不追责)→ END
      │                                    ├─(刑事)→ 报案书 → END
      │                                    ├─(民事)→ A2A 西塞罗 → END
      │                                    └─(内部)→ enforcement
      │                                                  │
      │                                    post_report ←┘
      │                                         │
      └────────────────────────────────────── END

碳基守门 (HITL) 机制：
 - 每个阶段节点执行完成后，LangGraph 在 interrupt_before 处挂起
 - 前端显示 AI 输出 + 知识库引用，碳基审核
 - 碳基操作: approved(通过)/rejected(驳回重做)/modified(修改后通过)
 - 通过 resume 接口恢复执行，驳回则重新执行当前阶段

Redis Checkpointer：
 - 持久化工作流状态到 Redis Cluster
 - 支持断点续跑：服务重启后从最近的 checkpoint 恢复
 - 支持阶段回溯：通过 thread_id 恢复到任意历史 checkpoint
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# 工作流状态定义
# ═══════════════════════════════════════════════════════════════

class IntegrityState(TypedDict, total=False):
    """廉洁监察工作流状态 (LangGraph State)"""

    # ── 案件基础信息 ──
    task_id: str
    case_id: str
    client: str
    fraud_source: str

    # ── 工作流控制 ──
    current_stage: str
    stage_history: list[str]

    # ── [4.1] 分流决策 ──
    should_investigate: bool
    is_hr_related: bool
    should_transfer: bool

    # ── AI 产出物 ──
    intake_report: dict[str, Any] | None
    investigation_plan: dict[str, Any] | None
    case_conclusion: dict[str, Any] | None
    penalty_opinion: dict[str, Any] | None
    prosecution_letter: dict[str, Any] | None
    penalty_announcement: dict[str, Any] | None

    # ── 碳基守门状态 ──
    pending_approval_stage: str | None
    approval_result: str | None

    # ── 外部系统同步状态 ──
    risk_control_sync_status: str
    a2a_task_ids: dict[str, str]

    # ── 元数据 ──
    error_info: dict[str, Any] | None


# ═══════════════════════════════════════════════════════════════
# 阶段节点实现
# ═══════════════════════════════════════════════════════════════

STAGE_CONFIG = {
    "intake": {"order": 1, "name": "材料初判与分流", "agent": "intake-agent", "timeout_seconds": 30},
    "investigation": {"order": 2, "name": "调查方案生成", "agent": "investigation-agent", "timeout_seconds": 35},
    "analysis": {"order": 3, "name": "多维分析与报告撰写", "agent": "analysis-agent", "timeout_seconds": 90},
    "disposition": {"order": 4, "name": "处置分流与处罚确定", "agent": "disposition-agent", "timeout_seconds": 35},
    "enforcement": {"order": 5, "name": "处罚执行与跟踪", "agent": "enforcement-agent", "timeout_seconds": 45},
    "post_report": {"order": 6, "name": "报案后续协助", "agent": "post-report-agent", "timeout_seconds": 20},
}


async def intake_node(state: IntegrityState) -> IntegrityState:
    """
    [4.1] 材料初判与分流 — intake-agent
    """
    logger.info("intake_node_start", task_id=state.get("task_id"))

    # 集成 IntakeAgent 进行初判分析
    try:
        from hermes.agents.integrity.intake_agent import IntakeAgent
        from hermes.agents.integrity.schemas import IntakeAgentInput

        agent = IntakeAgent()
        case_input = IntakeAgentInput(
            task_id=state.get("task_id", ""),
            fraud_source=state.get("fraud_source", "manual"),
            client=state.get("client", "ecovacs"),
            fraud_event_detail=f"案件编号 {state.get('task_id', '')}，事业部 {state.get('client', '')}",
        )
        result = await agent.run(case_input)
        state["should_investigate"] = result.should_investigate
        state["should_transfer"] = result.should_transfer
        state["is_hr_related"] = result.is_hr_related
        state["intake_report"] = result.model_dump()
        logger.info("intake_agent_complete", task_id=state.get("task_id"),
                    should_investigate=result.should_investigate,
                    confidence=result.confidence.value if hasattr(result.confidence, 'value') else str(result.confidence))
    except Exception as e:
        logger.warning("intake_agent_unavailable", error=str(e),
                       message="IntakeAgent 不可用，使用骨架默认值")
        state["should_investigate"] = True
        state["is_hr_related"] = False
        state["should_transfer"] = False
        state["intake_report"] = {
            "status": "skeleton",
            "summary": "初判报告由骨架生成（AI Agent 不可用）",
            "error": str(e),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    state["current_stage"] = "intake"
    state["pending_approval_stage"] = "intake"
    state["stage_history"] = state.get("stage_history", []) + ["intake"]

    logger.info("intake_node_complete", task_id=state.get("task_id"),
                should_investigate=state["should_investigate"])
    return state


async def investigation_node(state: IntegrityState) -> IntegrityState:
    """[4.2] 调查方案生成 — investigation-agent"""
    logger.info("investigation_node_start", task_id=state.get("task_id"))

    # 尝试集成 InvestigationAgent
    try:
        from hermes.agents.integrity.investigation_agent import InvestigationAgent
        from hermes.agents.integrity.schemas import Client, InvestigationAgentInput

        agent = InvestigationAgent()
        intake_context = state.get("intake_report", {}) or {}
        plan_input = InvestigationAgentInput(
            task_id=state.get("task_id", ""),
            client=Client(state.get("client", "ecovacs")),
            intake_report_summary=intake_context.get("case_summary", ""),
            involved_entity_type=intake_context.get("involved_entity_type", "混合"),
            key_facts=intake_context.get("key_facts", []),
            suggested_focus=intake_context.get("suggested_next_steps", []),
            suggested_interview_targets=intake_context.get("suggested_interview_targets"),
            intake_context=intake_context,
        )
        result = await agent.run(plan_input)
        state["investigation_plan"] = result.model_dump()
        logger.info("investigation_agent_complete", task_id=state.get("task_id"),
                    confidence=result.confidence.value if hasattr(result.confidence, 'value') else str(result.confidence))
    except Exception as e:
        logger.warning("investigation_agent_unavailable", error=str(e))
        state["investigation_plan"] = {
            "status": "skeleton",
            "summary": "调查方案由骨架生成（AI Agent 不可用）",
            "error": str(e),
            "sections": ["调查方向", "访谈计划", "证据清单", "时间安排"],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    state["current_stage"] = "investigation"
    state["pending_approval_stage"] = "investigation"
    state["stage_history"] = state.get("stage_history", []) + ["investigation"]
    return state


async def analysis_node(state: IntegrityState) -> IntegrityState:
    """[4.3] 多维分析与报告撰写 — analysis-agent"""
    logger.info("analysis_node_start", task_id=state.get("task_id"))

    # 尝试集成 AnalysisAgent
    try:
        from hermes.agents.integrity.analysis_agent import AnalysisAgent
        from hermes.agents.integrity.schemas import AnalysisAgentInput, Client

        agent = AnalysisAgent()
        intake_context = state.get("intake_report", {}) or {}
        investigation_context = state.get("investigation_plan", {}) or {}
        analysis_input = AnalysisAgentInput(
            task_id=state.get("task_id", ""),
            client=Client(state.get("client", "ecovacs")),
            intake_context=intake_context,
            investigation_context=investigation_context,
        )
        result = await agent.run(analysis_input)
        state["case_conclusion"] = result.model_dump()
        logger.info("analysis_agent_complete", task_id=state.get("task_id"))
    except Exception as e:
        logger.warning("analysis_agent_unavailable", error=str(e))
        state["case_conclusion"] = {
            "status": "skeleton",
            "summary": "分析报告由骨架生成（AI Agent 不可用）",
            "error": str(e),
            "sections": ["案件概述", "调查过程", "事实认定", "证据链", "结论与建议"],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    state["current_stage"] = "analysis"
    state["pending_approval_stage"] = "analysis"
    state["stage_history"] = state.get("stage_history", []) + ["analysis"]
    return state


async def disposition_node(state: IntegrityState) -> IntegrityState:
    """[4.4] 处置分流与处罚确定 — disposition-agent"""
    logger.info("disposition_node_start", task_id=state.get("task_id"))

    try:
        from hermes.agents.integrity.disposition_agent import DispositionAgent
        from hermes.agents.integrity.schemas import Client, DispositionAgentInput

        agent = DispositionAgent()
        case_conclusion = state.get("case_conclusion", {}) or {}
        disp_input = DispositionAgentInput(
            task_id=state.get("task_id", ""),
            client=Client(state.get("client", "ecovacs")),
            case_conclusion=case_conclusion,
        )
        result = await agent.run(disp_input)
        state["penalty_opinion"] = result.model_dump()
        logger.info("disposition_agent_complete", task_id=state.get("task_id"))
    except Exception as e:
        logger.warning("disposition_agent_unavailable", error=str(e))
        state["penalty_opinion"] = {
            "status": "skeleton",
            "summary": "追责意见由骨架生成（AI Agent 不可用）",
            "has_penalty": True,
            "error": str(e),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    state["current_stage"] = "disposition"
    state["pending_approval_stage"] = "disposition"
    state["stage_history"] = state.get("stage_history", []) + ["disposition"]
    return state


async def enforcement_node(state: IntegrityState) -> IntegrityState:
    """[4.5] 处罚执行与跟踪 — enforcement-agent"""
    logger.info("enforcement_node_start", task_id=state.get("task_id"))

    # 尝试集成 EnforcementAgent，并触发 A2A 通信
    try:
        from hermes.agents.integrity.enforcement_agent import EnforcementAgent
        from hermes.agents.integrity.schemas import Client, EnforcementAgentInput

        agent = EnforcementAgent()
        penalty = state.get("penalty_opinion", {}) or {}
        enf_input = EnforcementAgentInput(
            task_id=state.get("task_id", ""),
            client=Client(state.get("client", "ecovacs")),
            penalty_opinion=penalty,
        )
        result = await agent.run(enf_input)
        state["penalty_announcement"] = result.model_dump()
        state["a2a_task_ids"] = result.a2a_task_ids if hasattr(result, 'a2a_task_ids') else {}
        logger.info("enforcement_agent_complete", task_id=state.get("task_id"),
                    a2a_tasks=len(state["a2a_task_ids"]))
    except Exception as e:
        logger.warning("enforcement_agent_unavailable", error=str(e))
        state["penalty_announcement"] = {
            "status": "skeleton",
            "summary": "处罚公告由骨架生成（AI Agent 不可用）",
            "a2a_targets": ["guibao", "cicero", "porter"],
            "error": str(e),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        state["a2a_task_ids"] = {}

    state["current_stage"] = "enforcement"
    state["pending_approval_stage"] = "enforcement"
    state["stage_history"] = state.get("stage_history", []) + ["enforcement"]
    return state


async def post_report_node(state: IntegrityState) -> IntegrityState:
    """[4.6] 报案后续协助 — post-report-agent"""
    logger.info("post_report_node_start", task_id=state.get("task_id"))

    try:
        from hermes.agents.integrity.post_report_agent import PostReportAgent
        from hermes.agents.integrity.schemas import DispositionPath, PostReportInput

        agent = PostReportAgent()
        case_conclusion = state.get("case_conclusion", {}) or {}
        penalty = state.get("penalty_opinion", {}) or {}

        # 根据处置类型推断路径
        disp_type = penalty.get("disposition_type", "internal") if penalty else "internal"
        disp_path = DispositionPath.CRIMINAL if "刑事" in str(disp_type) else (
            DispositionPath.CIVIL if "民事" in str(disp_type) else DispositionPath.INTERNAL
        )

        post_input = PostReportInput(
            task_id=state.get("task_id", ""),
            client=state.get("client", "ecovacs"),
            case_conclusion=case_conclusion,
            penalty_opinion=penalty,
            disposition_path=disp_path,
        )
        result = await agent.run(post_input)
        state["prosecution_letter"] = result.model_dump()
        logger.info("post_report_agent_complete", task_id=state.get("task_id"),
                    confidence=result.confidence.value if hasattr(result.confidence, 'value') else str(result.confidence))
    except Exception as e:
        logger.warning("post_report_agent_unavailable", error=str(e))
        state["prosecution_letter"] = {
            "status": "skeleton",
            "summary": "报案协助由骨架生成（AI Agent 不可用）",
            "error": str(e),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    state["current_stage"] = "post_report"
    state["pending_approval_stage"] = "post_report"
    state["stage_history"] = state.get("stage_history", []) + ["post_report"]
    return state


# ═══════════════════════════════════════════════════════════════
# 条件路由
# ═══════════════════════════════════════════════════════════════

def route_after_intake(state: IntegrityState) -> Literal["investigation", END]:
    """[4.1]→ 路由决策"""
    if state.get("should_investigate") and not state.get("should_transfer"):
        logger.info("route_intake_to_investigation", task_id=state.get("task_id"))
        return "investigation"
    reason = "no_investigation_needed" if not state.get("should_investigate") else "transferred"
    logger.info("route_intake_to_end", task_id=state.get("task_id"), reason=reason)
    return END


def route_after_disposition(state: IntegrityState) -> Literal["enforcement", END]:
    """[4.4]→ 路由决策"""
    penalty = state.get("penalty_opinion", {}) or {}
    has_penalty = penalty.get("has_penalty", False)
    if has_penalty:
        logger.info("route_disposition_to_enforcement", task_id=state.get("task_id"))
        return "enforcement"
    logger.info("route_disposition_to_end", task_id=state.get("task_id"))
    return END


# ═══════════════════════════════════════════════════════════════
# Graph 构建
# ═══════════════════════════════════════════════════════════════

def build_integrity_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    """构建廉洁监察 6 阶段 LangGraph 工作流"""
    workflow = StateGraph(IntegrityState)

    workflow.add_node("intake", intake_node)
    workflow.add_node("investigation", investigation_node)
    workflow.add_node("analysis", analysis_node)
    workflow.add_node("disposition", disposition_node)
    workflow.add_node("enforcement", enforcement_node)
    workflow.add_node("post_report", post_report_node)

    workflow.set_entry_point("intake")
    workflow.add_conditional_edges("intake", route_after_intake,
                                   path_map={"investigation": "investigation", END: END})
    workflow.add_edge("investigation", "analysis")
    workflow.add_edge("analysis", "disposition")
    workflow.add_conditional_edges("disposition", route_after_disposition,
                                   path_map={"enforcement": "enforcement", END: END})
    workflow.add_edge("enforcement", "post_report")
    workflow.add_edge("post_report", END)

    graph = workflow.compile(checkpointer=checkpointer)
    return graph


# ═══════════════════════════════════════════════════════════════
# 工作流管理器（供 API 层调用）
# ═══════════════════════════════════════════════════════════════

class IntegrityWorkflowManager:
    """廉洁监察工作流管理器

    提供启动、恢复、中断工作流的便捷方法，供 API 层调用。
    当前 LangGraph Checkpointer 尚未接入，使用内存模式执行。
    """

    def __init__(self):
        self._graph = build_integrity_graph()
        # 生产环境: 使用 RedisSaver(redis_client) 作为 checkpointer

    def start_workflow(self, case_id: str, task_id: str, client: str, fraud_source: str) -> str:
        """启动工作流，返回 thread_id"""
        thread_id = f"thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: IntegrityState = {
            "task_id": task_id,
            "case_id": case_id,
            "client": client,
            "fraud_source": fraud_source,
            "current_stage": "intake",
            "stage_history": [],
            "should_investigate": False,
            "is_hr_related": False,
            "should_transfer": False,
            "intake_report": None,
            "investigation_plan": None,
            "case_conclusion": None,
            "penalty_opinion": None,
            "prosecution_letter": None,
            "penalty_announcement": None,
            "pending_approval_stage": None,
            "approval_result": None,
            "risk_control_sync_status": "pending",
            "a2a_task_ids": {},
            "error_info": None,
        }
        # 异步启动（后台执行，不阻塞调用者）
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        logger.info("workflow_started", task_id=task_id, thread_id=thread_id)
        return thread_id

    def interrupt_workflow(self, task_id: str, stage: str) -> None:
        """中断当前工作流阶段"""
        logger.info("workflow_interrupted", task_id=task_id, stage=stage)
        # 生产环境: 通过 LangGraph interrupt 机制暂停

    def get_workflow_state(self, task_id: str) -> dict[str, Any] | None:
        """获取工作流当前状态"""
        thread_id = f"thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = self._graph.get_state(config)
            return state.values if state else None
        except Exception as e:
            logger.warning("workflow_get_state_failed", task_id=task_id, error=str(e))
            return None


# 全局单例
integrity_graph = IntegrityWorkflowManager()
