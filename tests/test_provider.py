import json

import httpx
import pytest
from openai import OpenAI

from ape.provider import OpenAIProvider, ProviderFailure


@pytest.fixture
def sdk_client():
    """Use the installed SDK with a labeled HTTP transport double."""
    clients = []

    def build(handler):
        client = OpenAI(
            api_key="test-only",
            base_url="https://test.invalid/v1",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return OpenAIProvider(client)

    yield build
    for client in clients:
        client.close()


def test_sdk_request_and_actual_response(registry, sdk_client):
    paths = []

    def handle(req):
        paths.append(req.url.path)
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "test-strong",
                    "object": "model",
                    "created": 0,
                    "owned_by": "test",
                },
            )
        body = json.loads(req.content)
        assert body["model"] == "test-strong" and body["reasoning"] == {
            "effort": "high"
        }
        assert (
            body["max_output_tokens"] == 100
            and body["store"] is False
            and body["tool_choice"] == "none"
        )
        return httpx.Response(
            200,
            headers={"x-request-id": "http-id"},
            json={
                "id": "resp-id",
                "object": "response",
                "status": "completed",
                "model": "test-strong",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "id": "msg",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "A plan", "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 15,
                    "output_tokens": 10,
                    "total_tokens": 25,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 3},
                },
            },
        )

    res = sdk_client(handle).invoke(
        registry.model_aliases["strong"], "high", "plan", 100
    )
    assert paths == ["/v1/models/test-strong", "/v1/responses"]
    assert (res.text, res.request_id, res.response_id, res.actual_model) == (
        "A plan",
        "http-id",
        "resp-id",
        "test-strong",
    )
    assert (res.input_tokens, res.output_tokens, res.reasoning_tokens) == (15, 10, 3)


@pytest.mark.parametrize(
    ("code", "fallback"), [(403, False), (404, True), (429, True), (503, True)]
)
def test_sdk_preflight_failure(registry, sdk_client, code, fallback):
    def handle(req):
        assert req.method == "GET"
        return httpx.Response(code, json={"error": {"message": "test"}})

    with pytest.raises(ProviderFailure) as error:
        sdk_client(handle).invoke(registry.model_aliases["strong"], "high", "plan", 100)
    assert error.value.available_fallback == fallback
    assert error.value.code == f"http_{code}"
