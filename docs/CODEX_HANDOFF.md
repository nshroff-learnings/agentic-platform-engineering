# Codex Session Handoff

## Project boundary
APE is the new active project. SAT Studio PDLC is paused and remains separate. This repository is a design handoff, not an implemented agent platform.

## Mandatory reading
1. `AGENTS.md`
2. `docs/IMPLEMENTATION_BLUEPRINT.md`
3. `docs/ROADMAP.md`
4. `docs/MODEL_ROUTING.md`

## Initial Codex task
Inspect this repository. Propose the Phase 0 architecture only: Python module tree, dependencies, versioned Pydantic contracts, durable workflow state and migration plan, agent interface and model adapter, approval semantics, tool authorization, audit/events, FastAPI endpoints, test plan, and acceptance criteria. Clearly distinguish real SDK calls from placeholders. Do not write implementation code until the user approves. Do not implement Phase 1 or later. After approval, implement Phase 0, run actual tests, update the roadmap, and stop.

## User-approved direction
Request-driven first. Support infrastructure requests and bulk vulnerability remediation. Multi-format vulnerability intake must accept CSV, XLSX, Markdown and JSON (SARIF later/where practical), preserve original evidence and handle mixed uploads. Use human approval gates for designs, PRs and deployments. Start with Terraform request path, then AKS and vulnerability remediation.

## Model routing handoff
Read `docs/MODEL_ROUTING.md` and `config/model-routing.example.yaml`. Implement agent-specific runtime model selection during Phase 0 using logical model aliases, verified provider IDs, risk-based escalation and recorded model invocation evidence. Do not assume Codex itself switches its active model from Markdown instructions.
