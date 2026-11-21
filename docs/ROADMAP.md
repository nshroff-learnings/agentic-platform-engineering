# Implementation Roadmap

Phase 0 is implemented and locally verified. Phase 1 is ready for design approval.

- [x] Phase 0 — Local foundation with SQLite schema v1, durable dispatch, 13 registered roles, scoped tool access, versioned artifacts, approval gates, audit events, FastAPI and automated tests.
- [ ] Phase 1 — Request Analyst and Platform Architect: model-backed request analysis and approved design.
- [ ] Phase 2 — Terraform engineering: senior/junior agents, Git branches, fmt/validate/plan/security checks, PR.
- [ ] Phase 3 — AKS engineering: senior/junior agents, manifests/Helm, offline validation, PR.
- [ ] Phase 4 — Vulnerability remediation: multi-file CSV/XLSX/MD/JSON/SARIF parsing, normalization, dedupe, triage, grouping, remediation PRs.
- [ ] Phase 5 — DevOps, validation and SRE: pipeline execution, independent checks, approval and operational verification.
- [ ] Phase 6 — Enterprise: Azure DevOps, Entra ID, Foundry, Azure SQL/Blob/Service Bus, multi-tenancy, Splunk and scanner connectors.

At every phase: design review -> explicit approval -> implementation -> actual test evidence -> roadmap update -> stop for user review.

Model routing deliverables

- [x] Phase 0 — Model registry, OpenAI Responses adapter, role/risk policy, approved fallback rules, attempt evidence and routing tests.
- [ ] Phase 1–5: register each specialized agent with its model tier and enforce escalation policy.
- [ ] Phase 6: enterprise model governance, usage/cost telemetry, tenant-specific model allowlists.

## Phase 0 verification

Executed on 2026-11-20 in the repository root on Windows, using Python 3.13.3, pytest 9.0.3 and openai 2.3.0.

| Command | Observed result |
|---|---|
| `python -m pytest -q` | 44 passed in 3.81 seconds, exit 0 |
| `python -m ruff check src tests` | All checks passed, exit 0 |
| `python -m compileall -q src` | Exit 0 |

The initial suite found a DevOps default mismatch (1 failed, 37 passed). The example now sets medium reasoning for ordinary DevOps work. The final suite also exercises the installed provider SDK and local application factory.

- The API scenario submitted the private-endpoint storage request, recorded a design approval, reopened the database through a fresh app instance, blocked placeholder model IDs and persisted a human-authored task plan and change approval.
- Routing tests covered all 13 defaults, four risk levels, unknown scope, per-role configuration, budget and capability limits, explicit fallback, forbidden downgrades and attempt metadata.
- Gate and recovery tests covered cross-project access, self-review, rejection, stale versions, critical independent validation, concurrent dispatch, interruption and superseding an in-flight result.
- Provider tests used the installed OpenAI client with an HTTP transport double. Dispatcher tests used a labeled scripted provider. There was no configured deployment or runtime API key for a live smoke test. Live model identity, access, reasoning support and billing remain unverified.
- The local service accepts operator-reviewed structured risk facts. The artifact store uses checksummed, append-only SQLite records. Local database administrators remain trusted. The phase ends with reviewable plans and authorization records. No infrastructure commands or deployments were executed.

## Phase 1 proposal for review

Add Request Analyst and Platform Architect handlers under `src/ape/agents/`. Extend the existing contracts, dispatcher, state migration and API to persist structured requirements, clarification requests and architecture proposals before the existing design approval gate. Bind both outputs to their input revisions. Require approved requirements before architecture generation. Keep classification inputs and human decisions under workflow control.

Reuse the Phase 0 SDK adapter, router and SQLite store. A verified model configuration and provider credentials are dependencies for the live acceptance run. Malformed output, unresolved scope and stale revisions must stop advancement. Acceptance requires automated clarification, revision, restart and gate tests plus a real model-backed storage request with recorded model, usage and artifact provenance. Review Phase 1 results before Terraform, then AKS, then bulk vulnerability remediation.
