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

状态恢复 (Recovery)：
 - 工作流中断时调用 LangGraph get_state(thread_id) 获取当前状态
 - 调用 update_state 注入碳基修改内容
 - 调用 invoke(None, thread_id) 从 interrupt 点继续

外部集成：
 - intake: 风控系统字段 → Hermes 案件字段映射
 - disposition: 刑事路径生成报案书 → 同步风险监控
 - enforcement: 多路 A2A (龟宝/西塞罗/波特) + MDM 黑名单 + OA 审批

参考文档：
 - 架构设计: doc/architecture-design.md §4.2 模块一
 - Agent 设计: doc/agents/01-integrity-supervision-agents.md
 - API 设计: doc/api-design.md §3-5
"""

from __future__ import annotations

import asyncio
import uuid
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
    """廉洁监察工作流状态 (LangGraph State)

    该状态在 6 个阶段节点间流转，由 Redis Checkpointer 持久化。
    total=False 表示所有字段均为可选，初始状态可以部分填充。

    状态分类：
    - 案件基础: task_id, case_id, client, fraud_source
    - 分流决策: should_investigate, is_hr_related, should_transfer
    - AI 输出: 每个阶段一个产出物字典
    - 守门控制: pending_approval_stage, approval_result
    - 外部集成: risk_control_sync_status, a2a_task_ids
    """

    # ── 案件基础信息 ──
    task_id: str                # 案件编号，如 SD20260606001
    case_id: str                # 数据库 case UUID
    client: str                 # 事业部: ecovacs / tineco / group
    fraud_source: str           # 来源: manual / phone / email / wechat / agent

    # ── 工作流控制 ──
    current_stage: str          # 当前阶段: intake / investigation / analysis / ...
    stage_history: list[str]    # 已完成阶段列表 (追加模式)

    # ── 阶段 [4.1] 分流决策 ──
    should_investigate: bool    # 是否立案继续调查
    is_hr_related: bool         # 是否 HR 管辖 (需转交龟宝)
    should_transfer: bool       # 是否转交其他部门

    # ── AI 产出物 ──
    intake_report: dict[str, Any] | None           # [4.1] 初判报告
    investigation_plan: dict[str, Any] | None      # [4.2] 调查方案
    case_conclusion: dict[str, Any] | None         # [4.3] 案件结论 + 报告
    penalty_opinion: dict[str, Any] | None         # [4.4] 追责意见
    prosecution_letter: dict[str, Any] | None      # [4.4] 报案书 (刑事路径)
    penalty_announcement: dict[str, Any] | None    # [4.5] 处罚公告

    # ── 碳基守门状态 ──
    pending_approval_stage: str | None  # 当前等待守门的阶段名
    approval_result: str | None         # 守门结果: approved / rejected / modified

    # ── 外部系统同步状态 ──
    risk_control_sync_status: str       # 风控系统同步状态
    a2a_task_ids: dict[str, str]        # {agent_name: a2a_task_id} 映射

    # ── 元数据 ──
    error_info: dict[str, Any] | None   # 最近一次错误信息


# ═══════════════════════════════════════════════════════════════
# 阶段节点实现
# ═══════════════════════════════════════════════════════════════

# 阶段配置常量
STAGE_CONFIG = {
    "intake": {
        "order": 1,
        "name": "材料初判与分流",
        "agent": "intake-agent",
        "kb_types": ["intake", "common"],
        "tools": ["kb_search", "audio_transcribe_query", "es_search"],
        "timeout_seconds": 30,
    },
    "investigation": {
        "order": 2,
        "name": "调查方案生成",
        "agent": "investigation-agent",
        "kb_types": ["investigation", "common"],
        "tools": ["kb_search", "es_search"],
        "timeout_seconds": 35,
    },
    "analysis": {
        "order": 3,
        "name": "多维分析与报告撰写",
        "agent": "analysis-agent",
        "kb_types": ["analysis", "common"],
        "tools": ["kb_search", "es_search", "sql_analyze", "doc_generate"],
        "timeout_seconds": 90,
    },
    "disposition": {
        "order": 4,
        "name": "处置分流与处罚确定",
        "agent": "disposition-agent",
        "kb_types": ["disposition", "common"],
        "tools": ["kb_search", "doc_generate", "a2a_send"],
        "timeout_seconds": 35,
    },
    "enforcement": {
        "order": 5,
        "name": "处罚执行与跟踪",
        "agent": "enforcement-agent",
        "kb_types": ["enforcement", "disposition", "common"],
        "tools": ["a2a_send", "doc_generate", "kb_search"],
        "timeout_seconds": 45,
    },
    "post_report": {
        "order": 6,
        "name": "报案后续协助",
        "agent": "post-report-agent",
        "kb_types": ["common"],
        "tools": ["doc_generate"],
        "timeout_seconds": 20,
    },
}


async def intake_node(state: IntegrityState) -> IntegrityState:
    """
    [4.1] 材料初判与分流 — intake-agent

    职责:
    1. 检索知识库 (组织架构、制度法规、人员名单、供应商清单、历史案例)
    2. 分析案件材料 (举报文本、附件描述、语音转录结果)
    3. 评估线索可信度，判断案件性质和严重程度
    4. 做出分流决策: 不处理 / 转交 HR/法务 / 继续调查

    输入 (来自 state):
    - task_id, client, fraud_source: 案件基础信息
    - stage_history: 前一阶段的流转记录

    输出 (写入 state):
    - should_investigate: 是否立案
    - should_transfer: 是否转交
    - is_hr_related: 是否 HR 管辖
    - intake_report: 初判报告
    - pending_approval_stage: 设为 "intake" 触发守门

    路由:
    - should_investigate=True & should_transfer=False → investigation
    - 其他 → END
    """
    logger.info("intake_node_start", task_id=state.get("task_id"))

    # TODO: Phase 2 — 集成 IntakeAgent
    # from hermes.agents.integrity.intake_agent import IntakeAgent
    # agent = IntakeAgent()
    # result = await agent.run(case_input, kb_context=..., similar_cases_context=...)
    # state["should_investigate"] = result.should_investigate
    # state["should_transfer"] = result.should_transfer
    # state["is_hr_related"] = result.is_hr_related
    # state["intake_report"] = result.model_dump()

    # 当前骨架默认值: 默认立案继续调查
    state["should_investigate"] = True
    state["is_hr_related"] = False
    state["should_transfer"] = False
    state["intake_report"] = {
        "status": "pending",
        "summary": "初判报告待 AI 生成",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    state["current_stage"] = "intake"
    state["pending_approval_stage"] = "intake"
    state["stage_history"] = state.get("stage_history", []) + ["intake"]

    logger.info("intake_node_complete", task_id=state.get("task_id"),
                should_investigate=state["should_investigate"])
    return state


async def investigation_node(state: IntegrityState) -> IntegrityState:
    """
    [4.2] 调查方案生成 — investigation-agent

    职责:
    1. 基于初判报告和案件信息，检索历史类似案件及处理方案
    2. 检索相关法条和公司制度
    3. 生成结构化调查方案 (.xlsx):
       - 调查方向和重点
       - 访谈人员清单及提纲
       - 证据收集清单
       - 时间计划

    输入 (来自 state):
    - intake_report: 初判结果
    - task_id, client: 案件基础信息

    输出 (写入 state):
    - investigation_plan: 调查方案
    - pending_approval_stage: 设为 "investigation"
    """
    logger.info("investigation_node_start", task_id=state.get("task_id"))

    state["investigation_plan"] = {
        "status": "pending",
        "summary": "调查方案待 AI 生成",
        "sections": ["调查方向", "访谈计划", "证据清单", "时间安排"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    state["current_stage"] = "investigation"
    state["pending_approval_stage"] = "investigation"
    state["stage_history"] = state.get("stage_history", []) + ["investigation"]

    return state


async def analysis_node(state: IntegrityState) -> IntegrityState:
    """
    [4.3] 多维分析与报告撰写 — analysis-agent

    职责:
    1. 综合以下数据源进行多维分析:
       - 调查方案
       - 数据中台 SQL 分析结果 (业务数据异常透视)
       - 访谈记录 (语音转文字 + 人工整理)
       - 现场走访记录
       - ES 全文检索证据材料
       - PGVector 相似案例检索
    2. 生成标准化《廉洁监察报告》(Word):
       - 案件概述
       - 调查过程
       - 事实认定
       - 证据链
       - 结论与建议

    输入 (来自 state):
    - investigation_plan: 调查方案
    - task_id: 案件标识

    输出 (写入 state):
    - case_conclusion: 案件结论 + 报告路径
    - pending_approval_stage: 设为 "analysis"

    性能: P95 < 90s (三路检索并行 + 报告异步生成)
    """
    logger.info("analysis_node_start", task_id=state.get("task_id"))

    state["case_conclusion"] = {
        "status": "pending",
        "summary": "分析报告待 AI 生成",
        "sections": ["案件概述", "调查过程", "事实认定", "证据链", "结论与建议"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    state["current_stage"] = "analysis"
    state["pending_approval_stage"] = "analysis"
    state["stage_history"] = state.get("stage_history", []) + ["analysis"]

    return state


async def disposition_node(state: IntegrityState) -> IntegrityState:
    """
    [4.4] 处置分流与处罚确定 — disposition-agent

    职责:
    1. 根据案件结论确定法律路径:
       - 不追责 → END
       - 刑事犯罪 → 生成报案书、同步风险监控
       - 民事纠纷 → A2A 西塞罗 (法务智能体) 推送
       - 内部违规 → 追责意见 + 处罚建议
    2. 生成《追责意见书》:
       - 涉及人员及违规事实
       - 建议处罚类型 (警告/罚款/降级/开除)
       - 法律依据

    输入 (来自 state):
    - case_conclusion: 案件结论

    输出 (写入 state):
    - penalty_opinion: 追责意见
    - prosecution_letter: 报案书 (仅刑事路径)
    - pending_approval_stage: 设为 "disposition"

    路由:
    - has_penalty=True → enforcement
    - has_penalty=False → END
    """
    logger.info("disposition_node_start", task_id=state.get("task_id"))

    state["penalty_opinion"] = {
        "status": "pending",
        "summary": "追责意见待 AI 生成",
        "has_penalty": True,  # 骨架默认: 涉及追责
        "generated_at": datetime.now(UTC).isoformat(),
    }
    state["current_stage"] = "disposition"
    state["pending_approval_stage"] = "disposition"
    state["stage_history"] = state.get("stage_history", []) + ["disposition"]

    return state


async def enforcement_node(state: IntegrityState) -> IntegrityState:
    """
    [4.5] 处罚执行与跟踪 — enforcement-agent

    职责:
    1. 生成处罚公告 (Word)
    2. 发起 A2A 多路通信:
       - 龟宝 (guibao): initiate_penalty_tracking (员工处罚跟踪)
       - 西塞罗 (cicero): submit_agreement_review (协议审核)
       - 波特 (porter): initiate_supplier_deduction (供应商扣款)
    3. MDM 黑名单维护: 涉案供应商加入黑名单
    4. OA 同步: 添可事业部处罚公告 OA 审批推送
    5. 跟踪外部智能体回调和状态

    输入 (来自 state):
    - penalty_opinion: 追责意见
    - task_id: 案件标识

    输出 (写入 state):
    - penalty_announcement: 处罚公告
    - a2a_task_ids: 外部智能体任务 ID 映射
    - pending_approval_stage: 设为 "enforcement"

    降级策略:
    - 单个 A2A 通信失败不影响其他外部智能体调用
    - 全部 A2A 失败 → 降级为人工手动派发

    性能: P95 < 45s (多路 A2A 异步并行 + 文档异步生成)
    """
    logger.info("enforcement_node_start", task_id=state.get("task_id"))

    state["penalty_announcement"] = {
        "status": "pending",
        "summary": "处罚公告待 AI 生成",
        "a2a_targets": ["guibao", "cicero", "porter"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    state["a2a_task_ids"] = {}  # 初始化，后续填充实际 task_id
    state["current_stage"] = "enforcement"
    state["pending_approval_stage"] = "enforcement"
    state["stage_history"] = state.get("stage_history", []) + ["enforcement"]

    return state


async def post_report_node(state: IntegrityState) -> IntegrityState:
    """
    [4.6] 报案后续协助 — post-report-agent

    职责:
    1. 整理报案材料包 (案件报告 + 证据 + 报案书)
    2. 生成《报案后续协助指引》
    3. 同步风控系统: 闭环推送确认

    输入 (来自 state):
    - 所有前一阶段的产出物

    输出 (写入 state):
    - pending_approval_stage: 设为 "post_report"

    该阶段为最后一个节点，完成后工作流进入 END。
    """
    logger.info("post_report_node_start", task_id=state.get("task_id"))

    state["current_stage"] = "post_report"
    state["pending_approval_stage"] = "post_report"
    state["stage_history"] = state.get("stage_history", []) + ["post_report"]

    return state


# ═══════════════════════════════════════════════════════════════
# 条件路由
# ═══════════════════════════════════════════════════════════════

def route_after_intake(state: IntegrityState) -> Literal["investigation", END]:
    """
    [4.1]→ 路由决策

    条件:
    - should_investigate=True 且 should_transfer=False → investigation
    - 其他情况 (不处理 / 转交) → END

    转交场景 (END):
    - 不处理: 证据不足以调查 → 闭环推送风控系统 closure_confirmed
    - 转交 HR: is_hr_related=True → A2A 龟宝 (由 intake-agent 在节点内完成)
    - 转交其他部门: should_transfer=True → END
    """
    if state.get("should_investigate") and not state.get("should_transfer"):
        logger.info("route_intake_to_investigation", task_id=state.get("task_id"))
        return "investigation"

    reason = "no_investigation_needed" if not state.get("should_investigate") else "transferred"
    logger.info("route_intake_to_end", task_id=state.get("task_id"), reason=reason)
    return END


def route_after_disposition(state: IntegrityState) -> Literal["enforcement", END]:
    """
    [4.4]→ 路由决策

    条件:
    - penalty_opinion.has_penalty=True → enforcement
    - penalty_opinion.has_penalty=False → END

    无追责场景 (END):
    - 不追责 (证据不足 / 情节轻微)
    - 刑事路径 → 报案书已生成 (在 disposition 节点内完成)
    - 民事路径 → A2A 西塞罗 (在 disposition 节点内发送)
    """
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

def build_integrity_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> StateGraph:
    """构建廉洁监察 6 阶段 LangGraph 工作流

    使用方式:
        # 内嵌 checkpointer (Redis)
        from langgraph.checkpoint.redis import RedisSaver
        checkpointer = RedisSaver(redis_client)
        graph = build_integrity_graph(checkpointer)

        # 无 checkpointer (调试模式)
        graph = build_integrity_graph()

    运行方式:
        # 启动工作流
        initial_state = {"task_id": "SD20260606001", "case_id": "uuid", ...}
        config = {"configurable": {"thread_id": "thread-SD20260606001"}}
        result = await graph.ainvoke(initial_state, config)

        # 恢复工作流 (碳基守门后)
        result = await graph.ainvoke(None, config)

        # 查询状态
        state = graph.get_state(config)

    Args:
        checkpointer: LangGraph CheckpointSaver 实现 (Redis / Memory / Postgres)

    Returns:
        编译后的 StateGraph (可直接 await graph.ainvoke(...))

    节点注册顺序:
        1. 6 个阶段节点 (intake → investigation → analysis → disposition
           → enforcement → post_report)
        2. 入口: intake
        3. 条件边: intake → route_after_intake
        4. 直接边: investigation → analysis → disposition
        5. 条件边: disposition → route_after_disposition
        6. 直接边: enforcement → post_report → END

    interrupt_before 策略:
        - 在每个阶段节点之前挂起 (由 LangGraph interrupt_before 配置)
        - 初次启动: invoke 运行到第一个 interrupt 点 (intake 后)
        - 碳基守门后: invoke(None) 继续到下一个 interrupt 点
        - 使用方式:
            graph = workflow.compile(
                checkpointer=checkpointer,
                interrupt_before=[
                    "intake", "investigation", "analysis",
                    "disposition", "enforcement", "post_report",
                ],
            )
    """
    workflow = StateGraph(IntegrityState)

    # ── 添加节点 ──
    workflow.add_node("intake", intake_node)
    workflow.add_node("investigation", investigation_node)
    workflow.add_node("analysis", analysis_node)
    workflow.add_node("disposition", disposition_node)
    workflow.add_node("enforcement", enforcement_node)
    workflow.add_node("post_report", post_report_node)

    # ── 添加边 ──
    # 入口: START → intake
    workflow.set_entry_point("intake")

    # 条件路由: intake → investigation | END
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        path_map={
            "investigation": "investigation",
            END: END,
        },
    )

    # 顺序执行: investigation → analysis → disposition
    workflow.add_edge("investigation", "analysis")
    workflow.add_edge("analysis", "disposition")

    # 条件路由: disposition → enforcement | END
    workflow.add_conditional_edges(
        "disposition",
        route_after_disposition,
        path_map={
            "enforcement": "enforcement",
            END: END,
        },
    )

    # 顺序执行: enforcement → post_report → END
    workflow.add_edge("enforcement", "post_report")
    workflow.add_edge("post_report", END)

    # ── 编译 ──
    # 注意: 此处不传 interrupt_before，由上层调用者根据业务需要决定
    # 典型配置: interrupt_before=["investigation", "analysis", "disposition", "enforcement", "post_report"]
    # intake 后不 interrupt (intake 内自行设置 pending_approval_stage)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph
