"""
风险监控模块 — LangGraph 工作流定义

5 阶段工作流 + 智能异常哨兵 (7×24 无人值守自动扫描):

  主干流程:
    risk_rule → risk_scan → entity_merge → risk_classify → result_push

  异常哨兵 (条件触发):
    - after risk_scan:     deep_analysis (uncertain比例>30%)
    - after risk_scan:     schema_adaptation (SQL执行成功率<95%)
    - after risk_classify: rule_optimization (连续误报率>50%)
    - after risk_classify: novel_risk (发现新风险模式)

Agent 映射:
    risk-rule-agent      → risk_rule 节点
    risk-scan-agent      → risk_scan 节点 (SQL执行 + AI初核合并)
    risk-merge-agent     → entity_merge 节点
    risk-classify-agent  → risk_classify 节点
    系统编排               → result_push 节点
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class RiskMonitoringState(TypedDict, total=False):
    """风险监控工作流状态"""
    task_id: str
    current_stage: str
    stage_history: list[str]

    # 阶段输出
    risk_rules: list[dict[str, Any]]
    scan_output: dict[str, Any] | None
    anomaly_records: list[dict[str, Any]]
    merged_entities: list[dict[str, Any]]
    risk_classifications: list[dict[str, Any]]
    push_results: list[dict[str, Any]]

    # HITL 守门状态
    pending_approval_stage: str | None
    approval_result: str | None

    # 哨兵状态
    sentinel_flags: dict[str, Any]
    sentinel_triggered: str | None

    # 异常信息
    error_info: dict[str, Any] | None


# ═══════════════════════════════════════════════════════════════
# 阶段节点实现
# ═══════════════════════════════════════════════════════════════

STAGE_CONFIG = {
    "risk_rule": {"order": 1, "name": "风险规则清单生成", "agent": "risk-rule-agent", "timeout_seconds": 45},
    "risk_scan": {"order": 2, "name": "SQL执行 + AI初核异常", "agent": "risk-scan-agent", "timeout_seconds": 120},
    "entity_merge": {"order": 3, "name": "主体识别与合并去重", "agent": "risk-merge-agent", "timeout_seconds": 30},
    "risk_classify": {"order": 4, "name": "风险类型/等级判定", "agent": "risk-classify-agent", "timeout_seconds": 30},
    "result_push": {"order": 5, "name": "风险结果推送", "agent": "system", "timeout_seconds": 60},
}


async def risk_rule_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.1] 风险规则清单生成 — risk-rule-agent"""
    logger.info("risk_rule_node_start", task_id=state.get("task_id"))
    try:
        from hermes.agents.risk_monitoring.risk_rule_agent import RiskRuleAgent
        from hermes.schemas.agents.risk_monitoring import RiskRuleAgentInput, RuleGenerationMode

        _agent = RiskRuleAgent()
        _rule_input = RiskRuleAgentInput(
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
    """[6.2] SQL执行 + AI初核异常 — risk-scan-agent

    合并了原 risk_scan (SQL执行) 和 anomaly_filter (AI初核) 两个节点。
    risk-scan-agent 内部完成：
      1. SQL批量执行（由Celery Worker预执行，此处聚合结果）
      2. LLM AI初核：将每条异常分类为 normal/abnormal/uncertain
      3. 输出哨兵标记（deep_analysis_needed, schema_adaptation_needed）
    """
    logger.info("risk_scan_node_start", task_id=state.get("task_id"))
    try:
        from hermes.agents.risk_monitoring.risk_scan_agent import RiskScanAgent
        from hermes.schemas.agents.risk_monitoring import RiskExecutionMode, RiskScanAgentInput

        _agent = RiskScanAgent()
        _scan_input = RiskScanAgentInput(
            task_id=state.get("task_id", ""),
            execution_mode=RiskExecutionMode.SCHEDULED,
        )

        # 生产环境：此处从 Celery Worker 获取 SQL 执行结果
        # 当前骨架模式：使用空数据
        # result = await agent.run(db_session, scan_input, anomaly_results=sql_results)

        state["anomaly_records"] = []
        state["scan_output"] = {
            "status": "skeleton",
            "anomaly_summary": {"total_detected": 0, "ai_filtered_out": 0, "anomaly_confirmed": 0},
            "sentinel_flags": {
                "schema_adaptation_needed": False,
                "deep_analysis_needed": False,
            },
        }
    except Exception as e:
        logger.warning("risk_scan_agent_unavailable", error=str(e))
        state["anomaly_records"] = []
        state["scan_output"] = {
            "status": "skeleton",
            "error": str(e),
            "sentinel_flags": {"schema_adaptation_needed": False, "deep_analysis_needed": False},
        }

    state["current_stage"] = "risk_scan"
    state["pending_approval_stage"] = "risk_scan"
    state["stage_history"] = state.get("stage_history", []) + ["risk_scan"]
    return state


async def entity_merge_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.3] 主体识别与合并去重 — risk-merge-agent"""
    logger.info("entity_merge_node_start", task_id=state.get("task_id"))
    try:
        from hermes.agents.risk_monitoring.risk_merge_agent import RiskMergeAgent
        from hermes.schemas.agents.risk_monitoring import RiskMergeAgentInput

        _agent = RiskMergeAgent()
        _merge_input = RiskMergeAgentInput(
            task_id=state.get("task_id", ""),
            anomaly_records=[],
        )
        # result = await agent.run(db_session, merge_input)
        state["merged_entities"] = []
    except Exception as e:
        logger.warning("risk_merge_agent_unavailable", error=str(e))
        state["merged_entities"] = []

    state["current_stage"] = "entity_merge"
    state["stage_history"] = state.get("stage_history", []) + ["entity_merge"]
    return state


async def risk_classify_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.4] 风险类型/等级/处置建议判定 — risk-classify-agent"""
    logger.info("risk_classify_node_start", task_id=state.get("task_id"))
    try:
        from hermes.agents.risk_monitoring.risk_classify_agent import RiskClassifyAgent
        from hermes.schemas.agents.risk_monitoring import RiskClassifyAgentInput

        _agent = RiskClassifyAgent()
        _classify_input = RiskClassifyAgentInput(
            task_id=state.get("task_id", ""),
            merged_entities=[],
        )
        # result = await agent.run(db_session, classify_input)
        state["risk_classifications"] = []
    except Exception as e:
        logger.warning("risk_classify_agent_unavailable", error=str(e))
        state["risk_classifications"] = []

    state["current_stage"] = "risk_classify"
    state["pending_approval_stage"] = "risk_classify"
    state["stage_history"] = state.get("stage_history", []) + ["risk_classify"]
    return state


async def result_push_node(state: RiskMonitoringState) -> RiskMonitoringState:
    """[6.5] 风险结果推送 — 系统编排（非Agent）

    将定性后的风险结果推送至目标模块：
      → 廉洁监察 / 内控评价 / 商业秘密 / 行为风险 / 业务部门
    """
    logger.info("result_push_node_start", task_id=state.get("task_id"))
    state["current_stage"] = "result_push"
    state["push_results"] = []
    state["stage_history"] = state.get("stage_history", []) + ["result_push"]
    return state


# ═══════════════════════════════════════════════════════════════
# 异常哨兵节点 (条件触发，不可跳过主干)
# ═══════════════════════════════════════════════════════════════

SENTINEL_CONFIG = {
    "deep_analysis": {
        "trigger": "uncertain_ratio > 0.30",
        "description": "AI初核 uncertain 比例过高，触发深度分析",
        "action": "获取更多上下文后重新分析 → 更新 anomaly_records",
        "timeout_seconds": 60,
    },
    "schema_adaptation": {
        "trigger": "SQL执行成功率 < 95%",
        "description": "SQL执行失败率高，疑似Schema变更",
        "action": "Schema 变更推断 + SQL 修正建议 → 人工审核",
        "timeout_seconds": 30,
    },
    "rule_optimization": {
        "trigger": "某规则连续3次误报率 > 50%",
        "description": "规则误报率过高，建议优化",
        "action": "规则调整建议（SQL/阈值/范围）→ 人工审核",
        "timeout_seconds": 30,
    },
    "novel_risk": {
        "trigger": "发现超出已有规则覆盖的风险模式",
        "description": "检测到新型风险模式",
        "action": "新规则建议 → 进入 risk-rule-agent 流程",
        "timeout_seconds": 45,
    },
}


async def deep_analysis_sentinel(state: RiskMonitoringState) -> RiskMonitoringState:
    """哨兵：深度分析 — uncertain 比例过高时触发

    触发条件：scan_output.sentinel_flags.deep_analysis_needed == True
    输出：深度分析建议，更新 anomaly_records
    """
    logger.info(
        "deep_analysis_sentinel_triggered",
        task_id=state.get("task_id"),
        sentinel_flags=state.get("scan_output", {}).get("sentinel_flags", {}),
    )
    # TODO: 集成 deep-analysis-agent
    # agent = DeepAnalysisAgent()
    # result = await agent.run(db_session, anomaly_records=state["anomaly_records"])
    # state["anomaly_records"] = result.updated_records

    state["sentinel_triggered"] = "deep_analysis"
    state["sentinel_flags"]["deep_analysis_handled"] = True
    logger.info("deep_analysis_sentinel_complete", task_id=state.get("task_id"))
    return state


async def schema_adaptation_sentinel(state: RiskMonitoringState) -> RiskMonitoringState:
    """哨兵：Schema 适配 — SQL执行成功率低时触发

    触发条件：scan_output.sentinel_flags.schema_adaptation_needed == True
    输出：Schema 变更推断 + SQL 修正建议
    """
    logger.info(
        "schema_adaptation_sentinel_triggered",
        task_id=state.get("task_id"),
    )
    # TODO: 集成 schema-adaptation-agent
    # agent = SchemaAdaptationAgent()
    # result = await agent.run(db_session, failed_rules=state.get("failed_rules", []))
    # state["rule_adjustment_suggestions"] = result.suggestions

    state["sentinel_triggered"] = "schema_adaptation"
    state["sentinel_flags"]["schema_adaptation_handled"] = True
    logger.info("schema_adaptation_sentinel_complete", task_id=state.get("task_id"))
    return state


async def rule_optimization_sentinel(state: RiskMonitoringState) -> RiskMonitoringState:
    """哨兵：规则优化 — 误报率过高或低风险过多时触发

    触发条件：classify_output.sentinel_flags.rule_optimization_needed == True
    输出：规则调整建议
    """
    logger.info(
        "rule_optimization_sentinel_triggered",
        task_id=state.get("task_id"),
    )
    # TODO: 集成 rule-optimization-agent
    # agent = RuleOptimizationAgent()
    # result = await agent.run(db_session, risk_classifications=state["risk_classifications"])
    # state["rule_optimization_suggestions"] = result.suggestions

    state["sentinel_triggered"] = "rule_optimization"
    state["sentinel_flags"]["rule_optimization_handled"] = True
    logger.info("rule_optimization_sentinel_complete", task_id=state.get("task_id"))
    return state


async def novel_risk_sentinel(state: RiskMonitoringState) -> RiskMonitoringState:
    """哨兵：新型风险 — 发现超出已有规则覆盖的风险模式时触发

    触发条件：classify_output.sentinel_flags.novel_risk_detected == True
    输出：新规则建议
    """
    logger.info(
        "novel_risk_sentinel_triggered",
        task_id=state.get("task_id"),
    )
    # TODO: 集成 novel-risk-agent
    # agent = NovelRiskAgent()
    # result = await agent.run(db_session, novel_risk_description=...)
    # state["new_rule_suggestions"] = result.suggestions

    state["sentinel_triggered"] = "novel_risk"
    state["sentinel_flags"]["novel_risk_handled"] = True
    logger.info("novel_risk_sentinel_complete", task_id=state.get("task_id"))
    return state


# ═══════════════════════════════════════════════════════════════
# 哨兵路由判定 (确定性代码，非 LLM)
# ═══════════════════════════════════════════════════════════════

def route_after_risk_scan(state: RiskMonitoringState) -> Literal[
    "schema_adaptation_sentinel", "deep_analysis_sentinel", "entity_merge"
]:
    """risk_scan 之后的路由判定

    检查哨兵标记，优先处理需要人工关注的异常：
    1. Schema适配（SQL执行失败）> 深度分析（uncertain过多）> 正常流程
    """
    scan_output = state.get("scan_output", {}) or {}
    flags = scan_output.get("sentinel_flags", {})

    # 哨兵触发频率保护：如果已触发过，不再重复触发
    if state.get("sentinel_flags", {}).get("schema_adaptation_handled"):
        flags = {k: v for k, v in flags.items() if k != "schema_adaptation_needed"}
    if state.get("sentinel_flags", {}).get("deep_analysis_handled"):
        flags = {k: v for k, v in flags.items() if k != "deep_analysis_needed"}

    if flags.get("schema_adaptation_needed"):
        logger.info("route_to_schema_adaptation", task_id=state.get("task_id"))
        return "schema_adaptation_sentinel"
    if flags.get("deep_analysis_needed"):
        logger.info("route_to_deep_analysis", task_id=state.get("task_id"))
        return "deep_analysis_sentinel"

    logger.info("route_to_entity_merge", task_id=state.get("task_id"))
    return "entity_merge"


def route_after_schema_adaptation(state: RiskMonitoringState) -> Literal[
    "deep_analysis_sentinel", "entity_merge"
]:
    """Schema适配哨兵之后：继续检查是否需要深度分析"""
    scan_output = state.get("scan_output", {}) or {}
    flags = scan_output.get("sentinel_flags", {})

    if flags.get("deep_analysis_needed") and not state.get("sentinel_flags", {}).get("deep_analysis_handled"):
        logger.info("route_to_deep_analysis_after_schema", task_id=state.get("task_id"))
        return "deep_analysis_sentinel"

    return "entity_merge"


def route_after_risk_classify(state: RiskMonitoringState) -> Literal[
    "rule_optimization_sentinel", "novel_risk_sentinel", "result_push"
]:
    """risk_classify 之后的路由判定

    检查哨兵标记：
    1. 规则优化（低风险比例过高或外部信号）> 新型风险 > 正常推送
    """
    sentinel_flags = state.get("sentinel_flags", {})

    # 哨兵触发频率保护
    rule_opt_needed = sentinel_flags.get("rule_optimization_needed", False)
    novel_risk = sentinel_flags.get("novel_risk_detected", False)

    if rule_opt_needed and not sentinel_flags.get("rule_optimization_handled"):
        logger.info("route_to_rule_optimization", task_id=state.get("task_id"))
        return "rule_optimization_sentinel"
    if novel_risk and not sentinel_flags.get("novel_risk_handled"):
        logger.info("route_to_novel_risk", task_id=state.get("task_id"))
        return "novel_risk_sentinel"

    logger.info("route_to_result_push", task_id=state.get("task_id"))
    return "result_push"


# ═══════════════════════════════════════════════════════════════
# Graph 构建
# ═══════════════════════════════════════════════════════════════

def build_risk_monitoring_graph(checkpointer: BaseCheckpointSaver | None = None) -> StateGraph:
    """构建风险监控工作流 Graph（含哨兵子图）"""
    workflow = StateGraph(RiskMonitoringState)

    # ── 主干节点 ──
    workflow.add_node("risk_rule", risk_rule_node)
    workflow.add_node("risk_scan", risk_scan_node)
    workflow.add_node("entity_merge", entity_merge_node)
    workflow.add_node("risk_classify", risk_classify_node)
    workflow.add_node("result_push", result_push_node)

    # ── 哨兵节点 ──
    workflow.add_node("schema_adaptation_sentinel", schema_adaptation_sentinel)
    workflow.add_node("deep_analysis_sentinel", deep_analysis_sentinel)
    workflow.add_node("rule_optimization_sentinel", rule_optimization_sentinel)
    workflow.add_node("novel_risk_sentinel", novel_risk_sentinel)

    # ── 主干边 ──
    workflow.set_entry_point("risk_rule")
    workflow.add_edge("risk_rule", "risk_scan")

    # risk_scan → 条件路由 (哨兵判定)
    workflow.add_conditional_edges(
        "risk_scan",
        route_after_risk_scan,
        path_map={
            "schema_adaptation_sentinel": "schema_adaptation_sentinel",
            "deep_analysis_sentinel": "deep_analysis_sentinel",
            "entity_merge": "entity_merge",
        },
    )

    # 哨兵节点 → 回归主干或下一个哨兵
    workflow.add_conditional_edges(
        "schema_adaptation_sentinel",
        route_after_schema_adaptation,
        path_map={
            "deep_analysis_sentinel": "deep_analysis_sentinel",
            "entity_merge": "entity_merge",
        },
    )
    workflow.add_edge("deep_analysis_sentinel", "entity_merge")

    # 主干继续
    workflow.add_edge("entity_merge", "risk_classify")

    # risk_classify → 条件路由 (哨兵判定)
    workflow.add_conditional_edges(
        "risk_classify",
        route_after_risk_classify,
        path_map={
            "rule_optimization_sentinel": "rule_optimization_sentinel",
            "novel_risk_sentinel": "novel_risk_sentinel",
            "result_push": "result_push",
        },
    )

    # 哨兵节点 → 回归主干
    workflow.add_edge("rule_optimization_sentinel", "result_push")
    workflow.add_edge("novel_risk_sentinel", "result_push")

    # 终点
    workflow.add_edge("result_push", END)

    return workflow.compile(checkpointer=checkpointer)


# ═══════════════════════════════════════════════════════════════
# 工作流管理器（供 API 层调用）
# ═══════════════════════════════════════════════════════════════

class RiskMonitoringWorkflowManager:
    """风险监控工作流管理器

    管理 5 阶段主干 + 4 哨兵节点的风险监控工作流。
    支持：
      - 启动工作流
      - 中断/恢复工作流（HITL）
      - 查询工作流状态
    """

    def __init__(self):
        self._graph = build_risk_monitoring_graph()

    def start_workflow(self, task_id: str) -> str:
        """启动工作流，返回 thread_id"""
        thread_id = f"rm-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: RiskMonitoringState = {
            "task_id": task_id,
            "current_stage": "risk_rule",
            "stage_history": [],
            "risk_rules": [],
            "scan_output": None,
            "anomaly_records": [],
            "merged_entities": [],
            "risk_classifications": [],
            "push_results": [],
            "pending_approval_stage": None,
            "approval_result": None,
            "sentinel_flags": {},
            "sentinel_triggered": None,
            "error_info": None,
        }
        asyncio.create_task(self._graph.ainvoke(initial_state, config))
        logger.info(
            "risk_monitoring_workflow_started",
            task_id=task_id,
            thread_id=thread_id,
            stages=list(STAGE_CONFIG.keys()),
            sentinels=list(SENTINEL_CONFIG.keys()),
        )
        return thread_id

    def get_workflow_state(self, task_id: str) -> dict[str, Any] | None:
        """获取工作流当前状态"""
        thread_id = f"rm-thread-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = self._graph.get_state(config)
            return state.values if state else None
        except Exception as e:
            logger.warning("workflow_get_state_failed", task_id=task_id, error=str(e))
            return None


# 全局单例
risk_monitoring_graph = RiskMonitoringWorkflowManager()
