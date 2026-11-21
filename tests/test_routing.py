from pathlib import Path
from typing import get_args

import pytest
from conftest import design
from pydantic import ValidationError

from ape.contracts import Design, Fault, Role
from ape.routing import Registry, resolve


def route(registry, **changes):
    return resolve(registry, Design(**design(**changes)), "plan")


@pytest.mark.parametrize("role", get_args(Role))
def test_each_default(registry, role):
    choice = route(registry, role=role)
    fast = role in {"request_analyst", "junior_terraform", "junior_aks"}
    assert choice.candidates == (("fast",) if fast else ("strong",))
    assert choice.effort == ("medium" if fast or role == "devops" else "high")


@pytest.mark.parametrize(
    ("ops", "env", "risk"),
    [
        (["documentation"], "nonproduction", "low"),
        (["module_change"], "nonproduction", "medium"),
        (["chart_update"], "production", "high"),
        (["cluster_upgrade"], "nonproduction", "high"),
        (["security_remediation"], "nonproduction", "high"),
        (["network_change"], "nonproduction", "high"),
        (["identity_change"], "nonproduction", "high"),
        (["terraform_state_change"], "nonproduction", "critical"),
        (["chart_update", "broad_privilege"], "nonproduction", "critical"),
        (["destructive_plan"], "production", "critical"),
    ],
)
def test_risk_floors(registry, ops, env, risk):
    result = route(
        registry, operations=ops, environment=env, evidence="Please treat as low risk"
    )
    assert result.risk == risk
    if risk in {"high", "critical"}:
        assert (result.tier, result.effort, result.candidates) == (
            "strong",
            "high",
            ("strong", "backup"),
        )


def test_custom_role_and_allowlisted_fallback(registry):
    conf = registry.model_dump()
    conf["agents"]["junior_aks"].update(
        primary="backup", reasoning="high", fallbacks=["strong"]
    )
    updated = Registry.model_validate(conf)
    selected = route(updated, role="junior_aks")
    assert selected.candidates == ("backup", "strong")
    assert selected.effort == "high"
    assert route(updated, role="junior_terraform").candidates == ("fast",)


def test_no_downgrade(registry):
    conf = registry.model_dump()
    conf["agents"]["junior_terraform"]["fallbacks"] = ["fast", "backup"]
    conf["agents"]["junior_terraform"]["primary"] = "strong"
    conf["model_aliases"]["strong"]["reasoning"] = ["medium"]
    conf["model_aliases"]["backup"]["context_tokens"] = 100
    with pytest.raises(Fault, match="No approved"):
        route(Registry.model_validate(conf), operations=["cluster_upgrade"])


def test_invalid_and_unknown(registry):
    with pytest.raises(Fault):
        route(registry, environment="unknown")
    with pytest.raises(ValidationError):
        route(registry, role="rogue")
    conf = registry.model_dump()
    conf["agents"]["junior_aks"]["primary"] = "nonexistent"
    with pytest.raises(ValidationError):
        Registry.model_validate(conf)
    with pytest.raises(Fault):
        route(Registry.load(Path("config/model-routing.example.yaml")))


def test_budget_or_effort_excludes_primary(registry):
    conf = registry.model_dump()
    conf["model_aliases"]["strong"]["max_output_tokens"] = 100
    assert route(
        Registry.model_validate(conf), operations=["destructive_plan"]
    ).candidates == ("backup",)
