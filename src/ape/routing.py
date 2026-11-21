import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import Field, model_validator

from .contracts import Contract, Design, Effort, Fault, Name, Operation, Role, Tier


class Deployment(Contract):
    provider: Literal["openai"]
    model: Name
    tier: Tier
    reasoning: frozenset[Effort] = Field(min_length=1)
    context_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(ge=16)


class RolePolicy(Contract):
    tier: Tier
    reasoning: Effort
    primary: Name | None = None
    fallbacks: tuple[Name, ...] = ()


class Registry(Contract):
    version: Literal[1]
    output_tokens: int = Field(ge=16)
    model_aliases: dict[Name, Deployment]
    agents: dict[Role, RolePolicy]
    strong_fallbacks: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def check_references(self):
        if set(self.agents) != set(get_args(Role)):
            raise ValueError("Expected a policy for each registered role")
        for tier in ("fast", "strong"):
            if tier not in self.model_aliases or self.model_aliases[tier].tier != tier:
                raise ValueError(f"Invalid default alias {tier}")
        for role in self.agents.values():
            names = (role.primary or role.tier, *role.fallbacks)
            if any(name not in self.model_aliases for name in names):
                raise ValueError("Unknown deployment alias")
            if len(set(names)) != len(names):
                raise ValueError("Repeated fallback alias")
        if any(
            self.model_aliases.get(name) is None
            or self.model_aliases[name].tier != "strong"
            for name in self.strong_fallbacks
        ):
            raise ValueError("Invalid strong fallback")
        identities = [(d.provider, d.model) for d in self.model_aliases.values()]
        if len(set(identities)) != len(identities):
            raise ValueError("Configure each provider model only once")
        return self

    @classmethod
    def load(cls, path: Path):
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


CRITICAL = {
    Operation.STATE,
    Operation.DESTROY,
    Operation.PRIVILEGE,
    Operation.EMERGENCY,
}
HIGH = {Operation.UPGRADE, Operation.NETWORK, Operation.IDENTITY, Operation.SECURITY}


def assess(design: Design) -> tuple[str, list[str]]:
    if design.environment == "unknown":
        raise Fault("Target environment requires review")
    reasons = sorted(op.value for op in design.operations)
    if design.environment == "production":
        reasons.append("production")
    if CRITICAL & design.operations:
        return "critical", reasons
    if HIGH & design.operations or design.environment == "production":
        return "high", reasons
    if design.operations == {Operation.DOCUMENTATION}:
        return "low", reasons
    return "medium", reasons


@dataclass(frozen=True)
class Route:
    risk: str
    reasons: list[str]
    tier: Tier
    effort: Effort
    primary: str
    candidates: tuple[str, ...]
    policy_hash: str


def resolve(config: Registry, design: Design, prompt: str) -> Route:
    risk, reasons = assess(design)
    policy = config.agents[design.role]
    elevated = risk in {"high", "critical"}
    tier = "strong" if elevated else policy.tier
    effort = "high" if elevated else policy.reasoning
    primary = policy.primary or policy.tier
    if elevated and config.model_aliases[primary].tier != "strong":
        primary = "strong"
    names = (primary, *policy.fallbacks, *(config.strong_fallbacks if elevated else ()))
    # UTF-8 byte count conservatively bounds plain-text BPE input plus framing.
    required = len(prompt.encode("utf-8")) + 128 + config.output_tokens
    candidates = []
    for name in dict.fromkeys(names):
        deployment = config.model_aliases[name]
        if tier == "strong" and deployment.tier != "strong":
            continue
        if (
            effort in deployment.reasoning
            and required <= deployment.context_tokens
            and config.output_tokens <= deployment.max_output_tokens
            and not deployment.model.startswith("REPLACE_")
        ):
            candidates.append(name)
    if not candidates:
        raise Fault("No approved deployment satisfies this task")
    canonical = config.model_dump(mode="json")
    for deployment in canonical["model_aliases"].values():
        deployment["reasoning"].sort()
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()
    return Route(risk, reasons, tier, effort, primary, tuple(candidates), fingerprint)
