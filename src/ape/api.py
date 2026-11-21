import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .contracts import Decision, Design, Fault, Principal, Request, TaskPlan
from .dispatcher import Dispatcher
from .provider import OpenAIProvider
from .routing import Registry
from .store import Store, get_artifact, run_for
from .workflow import Workflow


def create_app(store, registry, provider, identities: dict[str, Principal]):
    app = FastAPI(title="APE local foundation", version="0.1.0")
    workflow = Workflow(store)
    dispatcher = Dispatcher(store, registry, provider)
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if credentials:
            digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
            if digest in identities:
                return identities[digest]
        raise HTTPException(
            401,
            "Valid local bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    Actor = Annotated[Principal, Depends(authenticate)]

    @app.exception_handler(Fault)
    async def fault_handler(request, exc):
        return JSONResponse({"detail": exc.reason}, status_code=exc.status)

    @app.post("/v1/requests", status_code=201)
    def submit(body: Request, actor: Actor):
        return workflow.submit(actor, body)

    @app.get("/v1/requests/{key}")
    def inspect(key: str, actor: Actor):
        return workflow.inspect(actor, key)

    @app.post("/v1/requests/{key}/designs")
    def design(key: str, body: Design, actor: Actor):
        return workflow.design(actor, key, body)

    @app.post("/v1/requests/{key}/plans")
    def plan(key: str, body: TaskPlan, actor: Actor):
        return workflow.plan(actor, key, body)

    @app.post("/v1/requests/{key}/decisions/{gate}")
    def decide(
        key: str,
        gate: Literal["design", "validation", "change"],
        body: Decision,
        actor: Actor,
    ):
        return workflow.decide(actor, key, body, gate)

    @app.get("/v1/requests/{key}/artifacts/{aid}")
    def read(key: str, aid: str, actor: Actor):
        with store.transaction() as db:
            run_for(db, actor, key)
            return dict(get_artifact(db, key, aid))

    @app.post("/v1/requests/{key}/tasks/{task_id}/invoke")
    def invoke(key: str, task_id: str, actor: Actor):
        return dispatcher.invoke(actor, key, task_id)

    @app.post("/v1/requests/{key}/tasks/{task_id}/reconcile")
    def reconcile(key: str, task_id: str, actor: Actor):
        return dispatcher.reconcile(actor, key, task_id)

    @app.post("/v1/requests/{key}/tasks/{task_id}/tools/{tool}")
    def tool(key: str, task_id: str, tool: str, actor: Actor):
        return workflow.read_tool(actor, key, task_id, tool)

    return app


def from_env():
    identity_file = Path(os.environ["APE_IDENTITIES"])
    identities = {
        key: Principal.model_validate(value)
        for key, value in json.loads(
            identity_file.read_text(encoding="utf-8-sig")
        ).items()
    }
    registry = Registry.load(
        Path(os.getenv("APE_ROUTING_CONFIG", "config/model-routing.example.yaml"))
    )
    return create_app(
        Store(Path(os.getenv("APE_DB", ".ape/state.sqlite3"))),
        registry,
        OpenAIProvider(),
        identities,
    )
