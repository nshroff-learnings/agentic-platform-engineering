import json

from .contracts import Decision, Design, Fault, Request, TaskPlan
from .routing import assess
from .store import artifact, event, get_artifact, require, run_for, uid


class Workflow:
    def __init__(self, store):
        self.store = store

    def submit(self, actor, request: Request):
        require(actor, "submit")
        key = uid()
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO runs(id,tenant,project,request,state) VALUES(?,?,?,?,?)",
                (
                    key,
                    actor.tenant,
                    actor.project,
                    request.model_dump_json(),
                    "Submitted",
                ),
            )
            event(db, key, actor.subject, "submitted", kind_requested=request.kind)
        return {"id": key, "state": "Submitted"}

    def inspect(self, actor, key):
        with self.store.transaction() as db:
            run = dict(run_for(db, actor, key))
            run["request"] = json.loads(run["request"])
            run["events"] = [
                dict(row) | {"data": json.loads(row["data"])}
                for row in db.execute(
                    "SELECT * FROM events WHERE run_id=? ORDER BY seq", (key,)
                )
            ]
            run["tasks"] = [
                dict(row)
                for row in db.execute("SELECT * FROM tasks WHERE run_id=?", (key,))
            ]
            return run

    def design(self, actor, key, design: Design):
        require(actor, "plan")
        with self.store.transaction() as db:
            run = run_for(db, actor, key)
            if run["revision"] != design.expected_revision:
                raise Fault("Stale design revision")
            db.execute(
                "UPDATE runs SET revision=revision+1,plan_id=NULL WHERE id=?", (key,)
            )
            run = run_for(db, actor, key)
            aid = artifact(db, run, "design", actor.subject, design.model_dump_json())
            try:
                risk, reasons = assess(design)
                state = "AwaitingDesignApproval"
            except Fault as error:
                risk, reasons, state = "unknown", [error.reason], "NeedsAttention"
            db.execute(
                "UPDATE runs SET design_id=?,state=? WHERE id=?", (aid, state, key)
            )
            db.execute(
                "UPDATE tasks SET status='Superseded' WHERE run_id=? AND status IN ('Queued','Running')",
                (key,),
            )
            event(
                db,
                key,
                actor.subject,
                "design_published",
                artifact_id=aid,
                risk=risk,
                reasons=reasons,
            )
            return {"artifact_id": aid, "state": state, "revision": run["revision"]}

    def decide(self, actor, key, decision: Decision, gate: str):
        validation = gate == "validation"
        require(actor, "validate" if validation else "approve")
        stages = {
            "design": ("AwaitingDesignApproval", "Planning", "DesignRevision"),
            "validation": (
                "AwaitingValidation",
                "AwaitingChangeApproval",
                "PlanRevision",
            ),
            "change": ("AwaitingChangeApproval", "ReadyForExecution", "PlanRevision"),
        }
        waiting, passed, rejected = stages[gate]
        with self.store.transaction() as db:
            run = run_for(db, actor, key)
            current = run["design_id" if gate == "design" else "plan_id"]
            if run["state"] != waiting or decision.artifact_id != current:
                raise Fault("Decision requires current artifact and pending gate")
            authors = {
                get_artifact(db, key, current)["author"],
                get_artifact(db, key, run["design_id"])["author"],
            }
            if actor.subject in authors:
                raise Fault("Independent decision required", 403)
            state = passed if decision.approved else rejected
            approval = event(
                db,
                key,
                actor.subject,
                "gate_decision",
                gate=gate,
                **decision.model_dump(),
            )
            db.execute("UPDATE runs SET state=? WHERE id=?", (state, key))
            if gate == "design" and decision.approved:
                db.execute(
                    "INSERT INTO tasks(id,run_id,design_id,status) VALUES(?,?,?,'Queued')",
                    (uid(), key, current),
                )
            return {"state": state, "decision_id": approval}

    def plan(self, actor, key, plan: TaskPlan):
        require(actor, "plan")
        with self.store.transaction() as db:
            run = run_for(db, actor, key)
            if (
                run["state"] not in {"Planning", "PlanRevision"}
                or plan.design_id != run["design_id"]
            ):
                raise Fault("Current approved design required")
            design = Design.model_validate_json(
                get_artifact(db, key, plan.design_id)["content"]
            )
            aid = artifact(db, run, "task_plan", actor.subject, plan.model_dump_json())
            state = (
                "AwaitingValidation"
                if assess(design)[0] == "critical"
                else "AwaitingChangeApproval"
            )
            db.execute(
                "UPDATE runs SET state=?,plan_id=? WHERE id=?", (state, aid, key)
            )
            db.execute(
                """UPDATE tasks SET status='Superseded' WHERE design_id=?
                          AND status IN ('Queued','Running')""",
                (plan.design_id,),
            )
            event(
                db,
                key,
                actor.subject,
                "plan_published",
                artifact_id=aid,
                design_id=plan.design_id,
            )
            return {"artifact_id": aid, "state": state}

    def read_tool(self, actor, key, task_id, tool):
        require(actor, "dispatch")
        with self.store.transaction() as db:
            run = run_for(db, actor, key)
            task = db.execute(
                "SELECT * FROM tasks WHERE run_id=? AND id=?", (key, task_id)
            ).fetchone()
            if not task or task["design_id"] != run["design_id"]:
                raise Fault("Current design approval required")
            design = get_artifact(db, key, task["design_id"])
            scope = Design.model_validate_json(design["content"]).allowed_tools
            if tool != "read_design" or tool not in scope:
                raise Fault("Tool outside approved scope", 403)
            event(db, key, actor.subject, "tool_read", task_id=task_id, tool=tool)
            return {
                "artifact_id": design["id"],
                "content": json.loads(design["content"]),
            }
