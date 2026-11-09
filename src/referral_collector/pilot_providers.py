"""Provider requests and usage normalization for the search pilot."""

from collections.abc import Callable
from dataclasses import dataclass

from anthropic import Anthropic
from google import genai
from google.genai import types
from openai import OpenAI


SDK_NAMES = {"anthropic": "anthropic", "openai": "openai", "gemini": "google-genai"}

# Standard input and output USD per million tokens, verified for the study panel.
RATES = {
    "claude-sonnet-4-5-20250929": (3, 15),
    "claude-sonnet-4-6": (3, 15),
    "claude-sonnet-5": (2, 10),
    "claude-sonnet-5-5": (2, 10),
    "gpt-4o-2024-08-06": (2.5, 10),
    "gpt-5.1-2025-11-13": (1.25, 10),
    "gpt-5.4": (2.5, 15),
    "gpt-6.1-sol": (2, 10),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3-flash-preview": (0.50, 3),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.8-flash": (0.75, 3.75),
}


def request_options(provider: str, model_id: str, prompt: str) -> dict:
    if provider == "anthropic":
        return {
            "model": model_id,
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        }
    if provider == "openai":
        return {
            "model": model_id,
            "input": prompt,
            "max_output_tokens": 1500,
            "max_tool_calls": 2,
            "tools": [{"type": "web_search", "external_web_access": True}],
            "include": ["web_search_call.action.sources"],
            "store": False,
        }
    return {
        "model": model_id,
        "contents": prompt,
        "config": {
            "max_output_tokens": 1500,
            "tools": [{"google_search": {}}],
            "automatic_function_calling": {"disable": True},
        },
    }


def request_search(provider: str, key: str, options: dict, capture: Callable[[bytes], None]) -> None:
    """Pass the unparsed HTTP body to capture, including provider error bodies."""
    if provider == "gemini":
        def capture_response(response):
            capture(response.read())

        http_options = types.HttpOptions(
            timeout=90_000,
            retry_options=types.HttpRetryOptions(attempts=1),
            client_args={"event_hooks": {"response": [capture_response]}},
        )
        with genai.Client(api_key=key, vertexai=False, http_options=http_options) as client:
            client.models.generate_content(**options)
        return

    client_type = Anthropic if provider == "anthropic" else OpenAI
    with client_type(api_key=key, max_retries=0, timeout=90) as client:
        resource = client.messages if provider == "anthropic" else client.responses
        try:
            response = resource.with_raw_response.create(**options)
        except Exception as error:
            if (response := getattr(error, "response", None)) is not None:
                capture(response.content)
            raise
        capture(response.http_response.content)


@dataclass(frozen=True)
class Observation:
    returned_model: str | None
    response_id: str | None
    usage: dict
    searches: int
    citations: int
    search_observed: bool
    complete: bool
    estimated_usd: float


def observe(provider: str, model_id: str, response: dict) -> Observation:
    input_rate, output_rate = RATES[model_id]
    if provider == "anthropic":
        usage = response["usage"]
        searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
        blocks = response.get("content") or []
        evidence = bool(searches and any(
            block.get("type") == "web_search_tool_result" and isinstance(block.get("content"), list)
            for block in blocks
        ))
        citations = sum(len(block.get("citations") or []) for block in blocks)
        billed_input = (
            usage["input_tokens"] + usage.get("cache_read_input_tokens", 0)
            + 2 * usage.get("cache_creation_input_tokens", 0)
        )
        billed_output = usage["output_tokens"]
        complete = response.get("stop_reason") == "end_turn"
        tool_cost = searches * 0.01
    elif provider == "openai":
        usage = response["usage"]
        items = response.get("output") or []
        search_calls = [
            item for item in items
            if item.get("type") == "web_search_call" and (item.get("action") or {}).get("type") == "search"
        ]
        searches = len(search_calls)
        evidence = any(item.get("status") == "completed" for item in search_calls)
        citations = sum(
            annotation.get("type") == "url_citation"
            for item in items for part in item.get("content", [])
            for annotation in part.get("annotations", [])
        )
        billed_input, billed_output = usage["input_tokens"], usage["output_tokens"]
        complete = response.get("status") == "completed"
        tool_cost = searches * 0.01
    else:
        usage = response["usageMetadata"]
        candidates = response.get("candidates") or [{}]
        candidate = candidates[0]
        grounding = candidate.get("groundingMetadata") or {}
        searches = len({query for query in grounding.get("webSearchQueries", []) if query.strip()})
        evidence = bool(searches and any(chunk.get("web") for chunk in grounding.get("groundingChunks", [])))
        citations = len({
            index for support in grounding.get("groundingSupports", [])
            for index in support.get("groundingChunkIndices", [])
        })
        billed_input = usage["promptTokenCount"] + usage.get("toolUsePromptTokenCount", 0)
        billed_output = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        complete = candidate.get("finishReason") == "STOP"
        # Price without free grounding allowances so the estimate errs high.
        tool_cost = 0.035 * bool(searches) if model_id == "gemini-2.5-flash" else 0.014 * searches

    cost = (billed_input * input_rate + billed_output * output_rate) / 1_000_000 + tool_cost
    return Observation(
        returned_model=response.get("model") or response.get("modelVersion"),
        response_id=response.get("id") or response.get("responseId"),
        usage=usage,
        searches=searches,
        citations=citations,
        search_observed=evidence,
        complete=complete,
        estimated_usd=round(cost, 8),
    )
