from dataclasses import dataclass
from typing import Protocol

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError

from .contracts import Effort
from .routing import Deployment


class ProviderFailure(Exception):
    def __init__(
        self, code: str, *, available_fallback: bool = False, uncertain: bool = False
    ):
        self.code = code
        self.available_fallback = available_fallback
        self.uncertain = uncertain
        super().__init__(code)


@dataclass(frozen=True)
class Result:
    text: str
    status: str
    actual_model: str | None
    request_id: str | None
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cost: float | None = None


class Provider(Protocol):
    def invoke(
        self, deployment: Deployment, effort: Effort, prompt: str, limit: int
    ) -> Result: ...


class OpenAIProvider:
    def __init__(self, client: OpenAI | None = None):
        self.client = client

    def invoke(self, deployment, effort, prompt, limit):
        dispatched = False
        try:
            client = self.client or OpenAI(max_retries=0, timeout=60)
            if client.models.retrieve(deployment.model).id != deployment.model:
                raise ProviderFailure("unverified_model")
            dispatched = True
            response = client.responses.create(
                model=deployment.model,
                input=prompt,
                reasoning={"effort": effort},
                max_output_tokens=limit,
                store=False,
                tool_choice="none",
                truncation="disabled",
            )
        except APIStatusError as exc:
            retry = exc.status_code == 429 or (
                not dispatched and exc.status_code in {404, 502, 503, 504}
            )
            raise ProviderFailure(
                f"http_{exc.status_code}",
                available_fallback=retry,
                uncertain=dispatched and exc.status_code >= 500,
            ) from exc
        except APIConnectionError as exc:
            raise ProviderFailure(
                "connection_failure",
                available_fallback=not dispatched,
                uncertain=dispatched,
            ) from exc
        except OpenAIError as exc:
            raise ProviderFailure(
                "provider_configuration_or_response", uncertain=dispatched
            ) from exc
        usage = response.usage
        detail = usage.output_tokens_details if usage else None
        return Result(
            response.output_text,
            response.status or "unknown",
            response.model,
            response._request_id,
            response.id,
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
            detail.reasoning_tokens if detail else None,
        )
