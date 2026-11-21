import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ape.api import create_app
from ape.contracts import Principal
from ape.provider import Result
from ape.routing import Registry
from ape.store import Store


class ScriptedProvider:
    """Test double. Never connects to a provider."""

    def __init__(self):
        self.calls = []
        self.script = []

    def invoke(self, model, effort, prompt, limit):
        self.calls.append((model.model, effort))
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        return Result(
            "Review this proposal",
            "completed",
            model.model,
            "req-test",
            "resp-test",
            23,
            9,
            4,
        )


@pytest.fixture
def registry():
    data = Registry.load(Path("config/model-routing.example.yaml")).model_dump()
    for name, model in data["model_aliases"].items():
        model["model"] = "test-" + name
    data["model_aliases"]["backup"] = dict(
        data["model_aliases"]["strong"], model="test-backup"
    )
    data["strong_fallbacks"] = ["backup"]
    return Registry.model_validate(data)


@pytest.fixture
def env(tmp_path, registry):
    store = Store(tmp_path / "state.sqlite")
    provider = ScriptedProvider()
    identities = {}
    for subject, project, rights in [
        ("author", "one", ["submit", "plan", "dispatch", "approve", "validate"]),
        ("reviewer", "one", ["approve", "validate"]),
        ("other", "two", ["approve", "dispatch"]),
        ("reader", "one", []),
    ]:
        digest = hashlib.sha256(subject.encode()).hexdigest()
        identities[digest] = Principal(
            subject=subject, tenant="org", project=project, rights=rights
        )
    client = TestClient(create_app(store, registry, provider, identities))

    def post(path, data=None, who="author"):
        return client.post(
            "/v1/requests" + path, json=data, headers={"Authorization": "Bearer " + who}
        )

    key = post(
        "", {"kind": "infrastructure", "description": "Plan private network access"}
    ).json()["id"]
    return store, provider, post, client, "/" + key


def design(**changes):
    return {
        "expected_revision": 0,
        "description": "Design for review",
        "environment": "nonproduction",
        "operations": ["module_change"],
        "evidence": "Operator reviewed change facts",
        "role": "junior_terraform",
        "allowed_tools": ["read_design"],
    } | changes


def queue(env, **changes):
    _, _, post, client, base = env
    aid = post(base + "/designs", design(**changes)).json()["artifact_id"]
    decision = {"approved": True, "artifact_id": aid, "reason": "Reviewed"}
    response = post(base + "/decisions/design", decision, who="reviewer")
    assert response.status_code == 200, response.text
    run = client.get(
        "/v1/requests" + base, headers={"Authorization": "Bearer author"}
    ).json()
    return aid, base + "/tasks/" + run["tasks"][-1]["id"]
