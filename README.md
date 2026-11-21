# Agentic Platform Engineering

APE is a request-driven Azure platform engineering system. The Phase 0 local API persists requests, design revisions, task plans, reviews, model attempts and evidence. The local workflow ends at `ReadyForExecution`. Phase status and verification results are in [the roadmap](docs/ROADMAP.md).

## Run the local API

Use Python 3.12 or later and run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m pytest -q
```

Create a private JSON identity file outside source control. Each key is the lowercase SHA-256 hex digest of a distinct high-entropy bearer token. Generate tokens with a cryptographic random generator and assign each human their own identity. The service derives tenant, project, subject and rights from this file. Each identity can inspect its project's requests and artifacts. Rights control writes, decisions and dispatch.

```json
{
  "<digest of engineer token>": {
    "subject": "engineer", "tenant": "local", "project": "demo", "rights": ["submit", "plan", "dispatch"]
  },
  "<digest of reviewer token>": {
    "subject": "reviewer", "tenant": "local", "project": "demo", "rights": ["approve", "validate"]
  }
}
```

```powershell
$env:APE_IDENTITIES = (Resolve-Path .ape/identities.json).Path
.\.venv\Scripts\python -m uvicorn ape.api:from_env --factory --host 127.0.0.1
```

Open `http://127.0.0.1:8000/docs` and use **Authorize** to supply the appropriate bearer token. The database defaults to `.ape/state.sqlite3`. Override it with `APE_DB`. Protect the identity file and database using local filesystem permissions. SQLite triggers enforce append-only application evidence. An administrator with direct filesystem access remains inside the local trust boundary.

## Exercise a request

1. Submit an infrastructure or remediation request. A planner publishes a design with `expected_revision: 0`, environment, reviewed operations, evidence, role and allowed tools.
2. A separate human approves the exact design artifact ID. Approval atomically queues a task. Rejection requests a revision. Publishing a newer design invalidates prior work.
3. A dispatcher can invoke the queued planning task. For live use, set `APE_ROUTING_CONFIG` to a verified routing file and configure `OPENAI_API_KEY` in the service environment. The example configuration supports offline review and blocks inference. A completed call produces an immutable proposal for the planner to review.
4. Publish the reviewed task plan against the current approved design. Critical changes require an independent validation decision. Change approval binds to the current plan artifact. The API exposes one scoped agent tool, `read_design`. Cloud execution belongs to later phases.
5. Inspect the request to see task IDs, decisions, attempt events and result references. The artifact endpoint returns the stored content and SHA-256 digest. A dispatcher can explicitly reconcile a stranded running task after investigating its provider outcome. Reconciliation records uncertainty. A fresh attempt requires a new approved design revision.

The restart test exercises this flow for an Azure Storage Account with a private endpoint and DNS. See [the test](tests/test_foundation.py), [routing configuration](config/model-routing.example.yaml), and [model routing policy](docs/MODEL_ROUTING.md).
