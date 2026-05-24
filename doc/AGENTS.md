# doc/ — 赫尔墨斯 设计文档

**All project substance lives here.** ~400KB of design specs in Chinese Markdown.

## OVERVIEW

4 master design documents + 8 module requirement specs defining a risk-control AI agent (LLM + RAG + A2A) for Ecovacs Group.

## STRUCTURE

```
doc/
├── hermes-requirements.md       # [71KB] Master requirements — 8 modules, dependency graph, business context
├── architecture-design.md       # [150KB] System architecture — LangGraph, K8s, CI/CD, multi-modal, observability
├── data-design.md               # [88KB] Data model — ~40 PostgreSQL tables, pgvector schema, RBAC, audit
├── api-design.md                # [57KB] REST API spec — endpoints, Pydantic schemas, auth flows
├── modules/                     # Per-module detailed requirements
│   ├── README.md                # Module index, dependency graph, shared infrastructure
│   ├── 01-integrity-supervision.md
│   ├── 02-risk-monitoring.md
│   ├── 03-internal-control-evaluation.md
│   ├── 04-special-audit.md
│   ├── 05-exit-audit.md
│   ├── 06-trade-secrets.md
│   ├── 07-behavioral-risk.md
│   └── 08-continuous-improvement.md
```

## WHERE TO LOOK

| Question | File | Section |
|----------|------|---------|
| What does the system do? | `hermes-requirements.md` | §1 (project overview, 8 modules) |
| How is it built? | `architecture-design.md` | §1-8 (full system design) |
| What's the DB schema? | `data-design.md` | all tables, ~40 total |
| What are the API routes? | `api-design.md` | grouped by domain |
| Module X details? | `modules/0X-*.md` | one file per module |
| How do modules relate? | `modules/README.md` | dependency graph + shared infra |
| How to deploy? | `architecture-design.md` | §6 (deployment, K8s, Helm) |
| How to test? | `architecture-design.md` | §8.9 (5 test types) |
| CI/CD pipeline? | `architecture-design.md` | §6.7 (GitLab CI, 4 stages) |

## CONVENTIONS (design docs)

- **Language**: Chinese content, English filenames (kebab-case)
- **Module numbering**: 00-08 (`00` = index/flowcharts)
- **API endpoints**: `/api/v1/{resource}`, snake_case query params
- **Response format**: `{"code": 0, "message": "", "data": {}}`
- **Auth**: JWT Bearer Token, RBAC 3 tiers
- **DB**: PostgreSQL 16 + pgvector, snake_case plural tables, UUID PKs, ISO 8601 timestamps
