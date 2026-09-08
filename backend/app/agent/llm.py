"""
The model behind a small interface.

The agent only ever sees `LLMClient`, so swapping Groq for another provider
is a config change rather than a rewrite. That matters here specifically
because we are on a free tier whose available models change over time.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from groq import BadRequestError, Groq

from app.config import get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    # A turn either asks for tools or answers; never usefully both.
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Set when the provider rejected the model's own tool call as malformed.
    # Carried rather than raised so the loop can ask for a correction.
    tool_error: str | None = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse: ...


class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        key = api_key or settings.groq_api_key
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to backend/.env before running a review."
            )
        self._client = Groq(api_key=key)
        self.model = model or settings.llm_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                temperature=temperature,
            )
        except BadRequestError as exc:
            # Groq validates tool arguments against the schema server-side and
            # returns 400 when the model gets them wrong. That is the model's
            # mistake, not ours, and it is recoverable: hand the message back
            # so the loop can ask for a corrected call.
            detail = _tool_use_error(exc)
            if detail is None:
                raise
            return LLMResponse(tool_error=detail)

        choice = response.choices[0].message
        usage = response.usage

        calls: list[ToolCall] = []
        for call in choice.tool_calls or []:
            calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=_parse_arguments(call.function.arguments),
                )
            )

        return LLMResponse(
            text=choice.content,
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


def _tool_use_error(exc: BadRequestError) -> str | None:
    """The message text if this was a rejected tool call, otherwise None so
    genuine request errors still surface as failures."""
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("code") == "tool_use_failed":
        return str(error.get("message", "Tool call validation failed"))
    return None


def _parse_arguments(raw: str | dict | None) -> dict[str, Any]:
    """
    Models occasionally emit malformed JSON for tool arguments. Returning an
    empty dict lets the tool layer reply with a validation error the model
    can correct on its next turn, instead of killing the whole review.
    """
    import json

    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_llm_client() -> LLMClient:
    return GroqClient()
