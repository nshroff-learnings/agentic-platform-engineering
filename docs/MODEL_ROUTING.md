# APE — LLM Selection and Routing Policy

## Two independent model-selection layers

1. **Codex development time**: Codex reads `AGENTS.md` and this document. These are instructions, **not** an automatic switch for the main Codex session. Select a model supported by the installed Codex version; optionally use supported model-configured subagents after verifying their behavior.
2. **APE runtime** uses the Python dispatcher to resolve the role and risk policy, invoke the configured provider, and record invocation evidence.

Model tiers below are **logical aliases**, not API model IDs. `strong` means the strongest verified reasoning/coding model approved in the environment; `fast` means a lower-latency approved coding/general model. If Astra/Sol models are available in the user's environment, they may be mapped to these aliases only after verifying the exact IDs and access. Do not assume identifiers such as `gpt-6-astra` exist.

## Agent-to-model mapping

| Agent | Default tier | Reasoning | Escalate when | Human gate |
|---|---|---|---|---|
| Request Analyst | fast | medium | Unclear scope, conflicting requests, sensitive data | Requirements approval |
| Orchestrator (LLM-assisted classification only) | strong | high | Ambiguous ownership, cross-project impact | Workflow engine enforces gates |
| Platform Architect | strong | high | Network topology, identity, production architecture | Design approval |
| Engineering Tech Lead | strong | high | Cross-service dependencies, risky assignments | Scope and PR review |
| Senior Terraform Engineer | strong | high | State migration, import, destroy, provider upgrade, networking | Plan and change approval |
| Junior Terraform Engineer | fast | medium | State changes, production resources, IAM, network exposure | Senior review + PR |
| Senior AKS Engineer | strong | high | Cluster upgrade, CNI, ingress, identity, node pools | Plan and change approval |
| Junior AKS Engineer | fast | medium | Privileged workloads, cluster-scoped permissions, production | Senior review + PR |
| Security Triage Agent | strong | high | Critical CVE, internet exposure, uncertain asset matching | Remediation scope approval |
| Vulnerability Remediation Agent | strong | high | IAM, RBAC, policies, network access, breaking fixes | Security review + PR |
| DevOps Engineer | strong | medium/high | Credentials, release gates, production pipeline changes | Pipeline/production approval |
| Independent Validation Agent | strong | high by default, medium configurable for ordinary tasks | Critical security or infrastructure changes | Cannot self-approve |
| SRE Engineer | strong | high | Incident impact, availability, production changes | Change approval |

### Risk overrides

- **Low**: documentation, non-production variable changes, routine unit tests → `fast` may be used, subject to ordinary review.
- **Medium**: standard module changes, Helm chart updates, non-prod pipeline modifications → `fast` for implementation if well-scoped, `strong` for review as needed.
- **High**: production infrastructure, AKS upgrades, RBAC/IAM, networking, private DNS, security remediations → `strong` and mandatory human review.
- **Critical**: Terraform state migration, destructive plan, broad privilege changes, emergency production remediation → `strong`, independent verification, explicit human authorization. Do not auto-apply.

Risk classification should be a deterministic policy decision using structured context and tool evidence; model advice may inform but never override policy.

## Runtime configuration contract

The executable v1 schema lives in `src/ape/routing.py`. Copy `config/model-routing.example.yaml` to a private operator-controlled configuration and select it with `APE_ROUTING_CONFIG`. The example loads for offline workflow use. Its placeholder IDs cannot dispatch a model request.

Each role has a tier, reasoning effort, optional primary alias and ordered optional `fallbacks`. A deployment specifies its exact provider model ID, approved tier, reasoning settings, context limit and output limit. Operators verify these capabilities for the target account. The OpenAI adapter retrieves the exact ID at invocation time, passes the configured effort and token limit to Responses, and accepts completed text only when the returned model matches the pin. Use dated, provider-verifiable IDs where the provider resolves a moving alias to a snapshot. Store credentials outside the YAML.

For example, to allow a backup for elevated risk, add a distinct verified deployment entry named `strong_backup` with tier `strong`, then set `strong_fallbacks: [strong_backup]`. For a single role, place the alias in that role's `fallbacks` instead. Each candidate must meet the effective tier, effort and token limits. The configured output budget and a conservative input-size estimate apply to each attempt.

A trusted planner records reviewed operations and target environment in a versioned design. Phase 0 derives risk from these structured fields. New evidence requires a revised design and approval. At high or critical risk the floor is strong/high. Unavailable capacity can trigger an approved fallback. An authorization failure stops dispatch. Ambiguous failures after sending a request require reconciliation. Each attempt produces audit evidence with the policy fingerprint, approval and tool scope linked through its task. Cost and token fields are nullable.

## Routing implementation requirements

1. Resolve request identity, tenant, project, environment, requested operation, and risk from trusted application context.
2. Determine agent role and risk override via explicit policy; resolve alias to verified provider/model configuration.
3. Reject unavailable high-risk models rather than silently downgrading. Permit fallback only from an explicit allowlist and record it.
4. Log agent role, task ID, model ID, reasoning setting, tool permissions, token usage/cost when available, fallback, and approval IDs.
5. Enforce allowed tools and human gates independently of model output. A model cannot grant its own permissions.
6. Keep generation and independent review separate; avoid allowing an agent to approve its own changes.
7. Test low/medium/high/critical routing, unknown models, model failure, fallback policy, and audit records.

## Codex implementation-time policy

- Use a verified strong model for Phase 0 orchestration, architecture, security boundaries, Terraform state, AKS networking, and production workflows.
- Use a verified faster model for narrow, low-risk scaffolding, schemas, docs, and unit tests where supported.
- `AGENTS.md` is advisory to Codex. Switching the current session's model is a Codex control, not a Markdown side effect.
- Model-configured Codex subagents are optional and version-dependent; verify configuration syntax and actual delegation before relying on them.
- Stop for approval at each implementation phase; do not confuse Codex coding subagents with APE runtime engineering agents.
