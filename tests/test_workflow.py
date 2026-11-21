import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from conftest import design, queue

from ape.provider import ProviderFailure, Result
from ape.store import Store


def snapshot(env):
    return (
        env[3]
        .get("/v1/requests" + env[4], headers={"Authorization": "Bearer author"})
        .json()
    )


def test_identity_and_workflow(env):
    _, _, post, client, base = env
    assert client.get("/v1/requests" + base).status_code == 401
    assert (
        post(
            "", {"kind": "infrastructure", "description": "test", "tenant": "foreign"}
        ).status_code
        == 422
    )
    assert post(base + "/designs", design(), who="other").status_code == 403
    assert (
        client.get(
            "/v1/requests" + base, headers={"Authorization": "Bearer other"}
        ).status_code
        == 404
    )
    r = post(base + "/designs", design(environment="unknown"))
    assert r.json()["state"] == "NeedsAttention"
    body = {
        "artifact_id": r.json()["artifact_id"],
        "approved": True,
        "reason": "reviewed",
    }
    assert post(base + "/decisions/design", body, "reviewer").status_code == 409
    aid = post(base + "/designs", design(expected_revision=1)).json()["artifact_id"]
    body.update(artifact_id=aid)
    assert post(base + "/decisions/design", body).status_code == 403
    assert post(base + "/decisions/design", body, "other").status_code == 404
    assert (
        post(base + "/decisions/design", body | {"approved": False}, "reviewer").json()[
            "state"
        ]
        == "DesignRevision"
    )
    assert (
        post(base + "/plans", {"design_id": aid, "content": "plan"}).status_code == 409
    )
    assert snapshot(env)["tasks"] == []


def test_critical_gates_and_artifact_revision(env):
    _, _, post, client, base = env
    old, stale_task = queue(env)
    current, task = queue(env, expected_revision=1, operations=["destructive_plan"])
    assert post(stale_task + "/tools/read_design").status_code == 409
    assert post(stale_task + "/invoke").status_code == 409
    assert post(task + "/tools/read_design").json()["artifact_id"] == current
    assert post(task + "/tools/terraform_apply").status_code == 403
    assert post(task + "/tools/read_design", who="reader").status_code == 403
    assert (
        post(base + "/plans", {"design_id": old, "content": "old"}).status_code == 409
    )

    def plan(content):
        r = post(base + "/plans", {"design_id": current, "content": content}).json()
        assert r["state"] == "AwaitingValidation"
        return {
            "artifact_id": r["artifact_id"],
            "approved": True,
            "reason": "Evidence reviewed",
        }

    body = plan("Plan v1")
    assert post(base + "/decisions/change", body, "reviewer").status_code == 409
    assert post(base + "/decisions/validation", body).status_code == 403
    assert (
        post(
            base + "/decisions/validation", body | {"approved": False}, "reviewer"
        ).json()["state"]
        == "PlanRevision"
    )
    new = plan("Plan v2")
    assert post(base + "/decisions/validation", body, "reviewer").status_code == 409
    assert post(base + "/decisions/validation", new, "reviewer").status_code == 200
    assert (
        post(base + "/decisions/change", new, "reviewer").json()["state"]
        == "ReadyForExecution"
    )
    r = client.get(
        "/v1/requests" + base + "/artifacts/" + new["artifact_id"],
        headers={"Authorization": "Bearer reviewer"},
    )
    assert json.loads(r.json()["content"])["content"] == "Plan v2"
    assert post(task + "/tools/deploy").status_code == 403


def test_fallback_audit_and_replay(env):
    store, provider, post, _, _ = env
    _, task = queue(env, operations=["cluster_upgrade"], allowed_tools=[])
    provider.script.append(ProviderFailure("http_429", available_fallback=True))
    result = post(task + "/invoke").json()
    assert result["status"] == "Completed"
    assert post(task + "/invoke").json() == result
    assert provider.calls == [("test-strong", "high"), ("test-backup", "high")]
    assert post(task + "/tools/read_design").status_code == 403
    events = snapshot(env)["events"]
    assert [
        e["data"]["fallback_reason"] for e in events if e["kind"] == "attempt_started"
    ] == [None, "http_429"]
    final = events[-1]["data"]
    assert final["metadata"]["actual_model"] == "test-backup"
    assert [
        final["metadata"][k]
        for k in ("input_tokens", "output_tokens", "reasoning_tokens")
    ] == [23, 9, 4]
    assert final["result_id"] == result["result_id"]
    with Store(store.path).transaction() as db:
        assert db.execute("SELECT status FROM tasks").fetchone()[0] == "Completed"
        for table in ("events", "artifacts"):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(f"DELETE FROM {table}")


@pytest.mark.parametrize(
    ("script", "calls"),
    [
        ([ProviderFailure("permission")], 1),
        ([ProviderFailure("timeout", uncertain=True)], 1),
        ([ProviderFailure("busy", available_fallback=True)] * 2, 2),
        ([Result("text", "completed", "wrong-model", None, None, None, None, None)], 1),
        ([Result("partial", "incomplete", "test-strong", None, None, 4, 0, None)], 1),
    ],
)
def test_failure_is_durable(env, script, calls):
    _, provider, post, _, _ = env
    _, task = queue(env, operations=["network_change"])
    provider.script.extend(script)
    assert post(task + "/invoke").json()["status"] == "NeedsAttention"
    assert len(provider.calls) == calls
    assert post(task + "/invoke").status_code == 409
    assert snapshot(env)["tasks"][0]["result_id"] is None


def test_unreported_usage(env):
    _, provider, post, _, _ = env
    _, task = queue(env)
    provider.script.append(
        Result("proposal", "completed", "test-fast", "req", "resp", None, None, None)
    )
    assert post(task + "/invoke").json()["status"] == "Completed"
    assert snapshot(env)["events"][-1]["data"]["metadata"]["input_tokens"] is None


def test_interrupted_attempt_survives_restart(env):
    store, provider, post, _, _ = env
    _, task = queue(env)
    provider.script.append(RuntimeError("simulated worker crash"))
    with pytest.raises(RuntimeError, match="simulated"):
        post(task + "/invoke")
    with Store(store.path).transaction() as db:
        assert db.execute("SELECT status FROM tasks").fetchone()[0] == "Running"
    assert post(task + "/invoke").status_code == 409
    assert post(task + "/reconcile").json()["status"] == "NeedsAttention"
    assert snapshot(env)["events"][-1]["data"]["outcome"] == "unknown"
    assert len(provider.calls) == 1


def test_concurrent_claim_and_revision(env, monkeypatch):
    _, provider, post, _, base = env
    _, task = queue(env)
    entered, resumed = Event(), Event()
    original = provider.invoke

    def delayed(*args):
        entered.set()
        assert resumed.wait(10)
        return original(*args)

    monkeypatch.setattr(provider, "invoke", delayed)
    with ThreadPoolExecutor() as pool:
        running = pool.submit(post, task + "/invoke")
        assert entered.wait(10)
        try:
            assert post(task + "/invoke").status_code == 409
            assert (
                post(base + "/designs", design(expected_revision=1)).status_code == 200
            )
        finally:
            resumed.set()
        assert running.result().json()["status"] == "Superseded"
    assert len(provider.calls) == 1
    assert snapshot(env)["tasks"][0]["result_id"] is None
