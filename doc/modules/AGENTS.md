# doc/modules/ — 模块需求文档

8 independent business module specifications, each defining a risk-control workflow. Source: PDF requirement extraction.

## OVERVIEW

| # | Module | File | Workflow |
|---|--------|------|----------|
| 01 | 廉洁监察 (Integrity Supervision) | `01-integrity-supervision.md` | 6-stage: intake → investigation → analysis → disposition → enforcement → post-report |
| 02 | 风险监控 (Risk Monitoring) | `02-risk-monitoring.md` | 6-stage: rule generation → anomaly detection → analysis → classification → push → feedback loop |
| 03 | 内控评价 (IC Evaluation) | `03-internal-control-evaluation.md` | 13-step: 19 business cycles, design + execution defects |
| 04 | 专项审计 (Special Audit) | `04-special-audit.md` | 5-stage: plan → interview → checklist → findings → report |
| 05 | 离任审计 (Exit Audit) | `05-exit-audit.md` | 6-stage: dual-track personal + business output |
| 06 | 商业秘密 (Trade Secrets) | `06-trade-secrets.md` | 3 functions: pre-review → classification review → management report |
| 07 | 行为风险 (Behavioral Risk) | `07-behavioral-risk.md` | Cross-system behavior analysis, anomaly detection |
| 08 | 持续改善 (Continuous Improvement) | `08-continuous-improvement.md` | PRD format: 36-field table, full lifecycle (submit → track → verify → close → archive) |

## MODULE DEPENDENCY GRAPH

```
                    M2 风险监控 (Push layer)
                    /           |           \
              ┌────┘          M3 内控     M6 商业秘密
           M1 廉洁              评价
              │                  │
              │        ┌─────────┘───────┐
              │        ▼                 ▼
              └──────→ M8 持续改善 (Sink) ←── M4 专项审计, M5 离任审计
```

DAG — no cycles. Push layer M2 → Execution (M1,M3,M6) → Sink M8. Parallel tier (M4,M5,M7) feed into M8 independently.

## WHERE TO LOOK

| Need | File |
|------|------|
| Module overview + dependency graph | `README.md` |
| Inter-module flowcharts | `00-index-flowcharts.md` |
| Shared infrastructure (RBAC, RAG, A2A, audit) | `README.md` §公共能力 |

## SHARED INFRASTRUCTURE

All modules depend on:
- **RBAC**: 3-tier (集团/科沃斯/添可)
- **RAG**: PGVector + Elasticsearch per-stage knowledge bases
- **A2A**: RabbitMQ communication with 龟宝(HR), 西塞罗(Legal), 波特(Finance)
- **Audit**: Immutable operation logs, 等保 level 2 compliance
- **Output**: Word/Excel export, in-text editing (划词调整)
