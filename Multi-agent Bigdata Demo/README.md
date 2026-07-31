# Multi-agent Bigdata Demo

This directory contains both the reusable Codex skill and the runnable Agentic Tax Bigdata Demo.

## Runnable demo

The application is under [`demo/`](demo/). It includes:

- FastAPI and LangGraph agent workflow;
- governed ChatBI with deterministic query contracts;
- integrated Chinese/English workbench;
- a Catalog -> Schema -> Table metadata center;
- schema, semantic metrics, privacy policy, lineage, and Iceberg snapshot views;
- artifact review, immutable release hashes, and persisted production approvals;
- four-eyes Huawei Cloud execution requests through a separate allowlisted worker;
- MRS, OBS, DataArts, Terraform, cleanup, and evidence scripts.

Start with [`demo/README.md`](demo/README.md). Real cloud writes are disabled by default.
Production deployment requirements are documented in
[`demo/docs/production-deployment.md`](demo/docs/production-deployment.md).

## Reusable skill

[`SKILL.md`](SKILL.md), [`references/`](references/), [`assets/`](assets/), and
[`agents/`](agents/) define the reusable implementation guidance and supporting artifacts.
