from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Name = Annotated[str, Field(min_length=1, max_length=160)]
Body = Annotated[str, Field(min_length=1, max_length=100_000)]
Role = Literal[
    "request_analyst",
    "orchestrator",
    "platform_architect",
    "engineering_tech_lead",
    "senior_terraform",
    "junior_terraform",
    "senior_aks",
    "junior_aks",
    "security_triage",
    "vulnerability_remediation",
    "devops",
    "validation",
    "sre",
]
Effort = Literal["low", "medium", "high"]
Tier = Literal["fast", "strong"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Principal(Contract):
    subject: Name
    tenant: Name
    project: Name
    rights: frozenset[Literal["submit", "plan", "approve", "validate", "dispatch"]]


class Request(Contract):
    kind: Literal["infrastructure", "remediation"]
    description: Body


class Operation(StrEnum):
    DOCUMENTATION = "documentation"
    MODULE = "module_change"
    CHART = "chart_update"
    PIPELINE = "pipeline_change"
    UPGRADE = "cluster_upgrade"
    NETWORK = "network_change"
    IDENTITY = "identity_change"
    SECURITY = "security_remediation"
    STATE = "terraform_state_change"
    DESTROY = "destructive_plan"
    PRIVILEGE = "broad_privilege"
    EMERGENCY = "emergency_production_remediation"


class Design(Contract):
    expected_revision: int = Field(ge=0)
    description: Body
    environment: Literal["nonproduction", "production", "unknown"]
    operations: frozenset[Operation] = Field(min_length=1)
    evidence: Body
    role: Role
    allowed_tools: frozenset[Literal["read_design"]] = frozenset()


class Decision(Contract):
    artifact_id: Name
    approved: bool
    reason: Name


class TaskPlan(Contract):
    design_id: Name
    content: Body


class Fault(Exception):
    def __init__(self, reason: str, status: int = 409):
        self.reason = reason
        self.status = status
        super().__init__(reason)
