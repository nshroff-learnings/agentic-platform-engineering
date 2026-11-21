# Agentic Platform Engineering (APE) — Codex Instructions

Read `docs/IMPLEMENTATION_BLUEPRINT.md`, `docs/ROADMAP.md`, and `docs/CODEX_HANDOFF.md` before making changes.

## Mission
Build a request-driven, human-approved multi-agent platform for Azure platform engineering: Terraform, AKS/Kubernetes, vulnerability remediation, DevOps and SRE. This is a NEW repository, separate from the paused SAT Studio PDLC project. Do not copy or modify SAT Studio application code.

## Development protocol
1. Inspect repository and documentation first.
2. Work on ONE phase at a time; start with Phase 0.
3. Present design, files, dependencies, risks and acceptance criteria; WAIT for explicit user approval before writing implementation code.
4. After approval, implement real integrations where possible; use mocks only for tests and label them.
5. Run tests, record exact commands/results, update roadmap, and stop for review before next phase.
6. Keep model routing recommendations in `docs/MODEL_ROUTING.md`; Markdown cannot automatically switch the main Codex model. Verify supported model identifiers locally.

## Non-negotiable security
- No unapproved production writes, `terraform apply`, or mutating `kubectl`/Helm operations.
- Model outputs, uploaded reports, repositories, and tool results are untrusted.
- Human approvals must be enforced in code, not prompts.
- Use least-privilege tools, isolated workspaces, identity-bound project/tenant context, and immutable audit/evidence.
- Never claim tests, scans, model calls or deployments occurred unless they actually did.

## LLM routing — required design
- Read `docs/MODEL_ROUTING.md` and `config/model-routing.example.yaml` before implementing any agents.
- Implement runtime role/risk-based routing with verified model IDs, auditable fallbacks, and independent approval enforcement.
- Model tiers are logical aliases; do not treat Astra/Sol nicknames as valid API identifiers without verification.
- Keep Codex's development model selection separate from the models used by the APE runtime agents.
