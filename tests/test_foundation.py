import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from ape.api import from_env


def test_local_factory_and_restart(tmp_path, monkeypatch):
    identity = tmp_path / "identities.json"
    identity.write_text(
        json.dumps(
            {
                hashlib.sha256(name.encode()).hexdigest(): {
                    "subject": name,
                    "tenant": "tenant",
                    "project": "project",
                    "rights": rights,
                }
                for name, rights in [
                    ("engineer", ["submit", "plan", "dispatch"]),
                    ("approver", ["approve"]),
                ]
            }
        )
    )
    monkeypatch.setenv("APE_DB", str(tmp_path / "requests.sqlite"))
    monkeypatch.setenv("APE_IDENTITIES", str(identity))
    monkeypatch.setenv(
        "APE_ROUTING_CONFIG", str(Path("config/model-routing.example.yaml").resolve())
    )
    auth = {"Authorization": "Bearer engineer"}
    review = {"Authorization": "Bearer approver"}
    with TestClient(from_env()) as api:
        assert api.get("/openapi.json").status_code == 200
        run = api.post(
            "/v1/requests",
            headers=auth,
            json={
                "kind": "infrastructure",
                "description": "Provision an Azure Storage Account using an approved Terraform module with private endpoint and DNS.",
            },
        )
        assert run.status_code == 201
        path = "/v1/requests/" + run.json()["id"]
        published = api.post(
            path + "/designs",
            headers=auth,
            json={
                "description": "Review module inputs, subnet and private DNS ownership",
                "expected_revision": 0,
                "operations": ["network_change"],
                "environment": "nonproduction",
                "role": "engineering_tech_lead",
                "evidence": "Private endpoint and DNS required",
            },
        )
        aid = published.json()["artifact_id"]
        decision = {"artifact_id": aid, "approved": True, "reason": "Reviewed scope"}
        assert (
            api.post(
                path + "/decisions/design", headers=review, json=decision
            ).status_code
            == 200
        )
    with TestClient(from_env()) as api:
        data = api.get(path, headers=auth).json()
        assert data["state"] == "Planning" and data["tasks"][0]["status"] == "Queued"
        dispatch = api.post(
            path + "/tasks/" + data["tasks"][0]["id"] + "/invoke", headers=auth
        )
        assert dispatch.json()["status"] == "NeedsAttention"
        plan = api.post(
            path + "/plans",
            headers=auth,
            json={
                "design_id": aid,
                "content": "Confirm subnet, review DNS zone link, prepare module inputs and request a plan review.",
            },
        )
        assert plan.json()["state"] == "AwaitingChangeApproval"
        decision["artifact_id"] = plan.json()["artifact_id"]
        assert (
            api.post(path + "/decisions/change", headers=review, json=decision).json()[
                "state"
            ]
            == "ReadyForExecution"
        )
        events = api.get(path, headers=auth).json()["events"]
        assert "route_blocked" in [e["kind"] for e in events]
        assert "attempt_started" not in [e["kind"] for e in events]
