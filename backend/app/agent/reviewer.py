"""
The review agent: a tool-calling loop, not a fixed pipeline.

The model is given the diff and a set of tools, and decides for itself what
to investigate. A rename may need no tool calls at all; a change to an auth
or payment path should pull callers and look for precedent before it
concludes anything. That decision is the model's, which is what makes this
an agent rather than a prompt template.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent.llm import LLMClient, get_llm_client
from app.agent.tool_registry import TOOL_DEFINITIONS, ToolExecutor
from app.config import get_settings

logger = logging.getLogger("agent")

SYSTEM_PROMPT = """\
You are a senior engineer reviewing a pull request. You have tools that let \
you investigate the repository this diff belongs to, and you are expected to \
use them before drawing conclusions that depend on code you cannot see.

How to work:
- Judge how much investigation the change actually warrants. A rename or a \
comment change may need none. A change to authentication, payments, data \
deletion, or a shared utility warrants finding out who depends on it.
- Before claiming a change is safe or that something is unused, check with \
find_callers. An empty diff context is not evidence of no usage.
- Use search_code to find how the repository already does something, so your \
suggestions match existing conventions instead of your own preferences.
- Prefer reading the real code over guessing at it.

When you are done investigating, reply with ONLY a JSON object, no prose and \
no code fences, in this shape:

{
  "summary": "one or two sentences on what this PR does and its overall risk",
  "findings": [
    {
      "severity": "critical" | "high" | "medium" | "low" | "info",
      "title": "short description of the issue",
      "body": "what is wrong and why it matters, in specific terms",
      "file": "path/to/file.py or null",
      "line": 123 or null,
      "evidence": "which tool results support this, or null if from the diff alone"
    }
  ]
}

Rules for findings:
- Only report things you are confident about, with a reason. An empty \
findings list is a perfectly good answer for a clean PR.
- Do not invent file paths, line numbers, or symbols. Every path you cite \
must come from the diff or from a tool result.
- Do not pad the list with style nitpicks unless they genuinely matter.
"""


@dataclass
class Finding:
    severity: str
    title: str
    body: str
    file: str | None = None
    line: int | None = None
    evidence: str | None = None


@dataclass
class ReviewResult:
    summary: str
    findings: list[Finding] = field(default_factory=list)
    # The investigation trail, so a review can show its work.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    steps_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: str | None = None


def _format_diff(
    pull_request: dict[str, Any],
    max_patch_chars: int = 6000,
    max_total_chars: int = 40000,
) -> str:
    """
    A per-file cap alone is not enough: fifty files at six thousand
    characters each would be a three hundred thousand character prompt. So
    there is an overall budget too, and the full file list is always shown
    even when the patches stop, so the agent knows what it has not seen and
    can go read those files with its tools.
    """
    changed_files = pull_request["changed_files"]
    lines = [
        f"PR #{pull_request['number']}: {pull_request['title']}",
        f"Author: {pull_request.get('author')}   "
        f"{pull_request.get('base_ref')} <- {pull_request.get('head_ref')}",
    ]
    if pull_request.get("body"):
        lines.append(f"\nDescription:\n{pull_request['body'][:1500]}")

    lines.append(f"\nChanged files ({len(changed_files)}):")
    for changed in changed_files:
        lines.append(
            f"  {changed['path']} ({changed['status']}, "
            f"+{changed['additions']}/-{changed['deletions']})"
        )

    # Smallest diffs first, so a budget spent on one enormous generated file
    # does not crowd out a dozen small, meaningful ones.
    by_size = sorted(changed_files, key=lambda f: len(f.get("patch") or ""))

    lines.append("\nPatches:")
    used = 0
    omitted: list[str] = []
    for changed in by_size:
        patch = changed.get("patch")
        if not patch:
            # Binary files and very large diffs come back without a patch.
            omitted.append(changed["path"])
            continue
        snippet = patch[:max_patch_chars]
        if used + len(snippet) > max_total_chars:
            omitted.append(changed["path"])
            continue
        lines.append(f"\n--- {changed['path']}")
        lines.append(snippet)
        if len(patch) > len(snippet):
            lines.append(f"... (patch truncated, {len(patch) - len(snippet)} more characters)")
        used += len(snippet)

    if omitted:
        lines.append(
            "\nPatches not shown for these files (use read_file if you need them): "
            + ", ".join(omitted)
        )
    return "\n".join(lines)


def review_pull_request(
    repository_id: int,
    pull_request: dict[str, Any],
    db: Session,
    llm: LLMClient | None = None,
    source=None,
    on_step: Callable[[int, str], None] | None = None,
) -> ReviewResult:
    settings = get_settings()
    llm = llm or get_llm_client()
    executor = ToolExecutor(repository_id, db, source)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Review this pull request. Investigate with the tools as needed, "
                "then reply with the JSON object.\n\n"
                + _format_diff(pull_request, max_total_chars=settings.agent_max_diff_chars)
            ),
        },
    ]

    prompt_tokens = completion_tokens = 0
    started = time.monotonic()

    for step in range(1, settings.agent_max_steps + 1):
        messages = _trim_history(messages, settings.agent_max_prompt_chars)
        response = llm.chat(messages, tools=TOOL_DEFINITIONS)
        prompt_tokens += response.prompt_tokens
        completion_tokens += response.completion_tokens

        if response.tool_error:
            # The provider rejected the model's tool call before it reached
            # us. Tell it what was wrong and let it try again.
            logger.info("step %d: tool call rejected, asking for a correction", step)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your last tool call was rejected: {response.tool_error}\n"
                        "Call the tool again with arguments matching its schema exactly, "
                        "or continue without it."
                    ),
                }
            )
            continue

        if not response.wants_tools:
            logger.info(
                "agent finished after %d step(s) in %.1fs (%d tool calls)",
                step,
                time.monotonic() - started,
                len(executor.calls_made),
            )
            result = _parse_review(response.text)
            result.tool_calls = executor.calls_made
            result.steps_used = step
            result.prompt_tokens = prompt_tokens
            result.completion_tokens = completion_tokens
            result.raw_response = response.text
            return result

        # The assistant turn must be echoed back verbatim alongside the tool
        # results, or the next turn has no record of what it asked for.
        messages.append(
            {
                "role": "assistant",
                "content": response.text or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in response.tool_calls
                ],
            }
        )

        for call in response.tool_calls:
            logger.info("step %d: %s(%s)", step, call.name, call.arguments)
            if on_step is not None:
                on_step(step, f"{call.name}({_short_args(call.arguments)})")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": executor.run(call.name, call.arguments),
                }
            )

    # Out of steps. Ask once more without tools so the work done so far still
    # produces a review, rather than throwing it all away.
    logger.warning("agent hit the %d step ceiling, forcing a summary", settings.agent_max_steps)
    messages.append(
        {
            "role": "user",
            "content": "Stop investigating and reply with the JSON object now, based on what you have.",
        }
    )
    final = llm.chat(messages, tools=None)
    result = _parse_review(final.text)
    result.tool_calls = executor.calls_made
    result.steps_used = settings.agent_max_steps
    result.prompt_tokens = prompt_tokens + final.prompt_tokens
    result.completion_tokens = completion_tokens + final.completion_tokens
    result.raw_response = final.text
    return result


def _history_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages)


def _trim_history(messages: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """
    Shrink the conversation to fit the budget by shortening the oldest tool
    results first. Their content is replaced rather than removed, because a
    tool message must stay paired with the assistant turn that asked for it;
    dropping one outright makes the next request invalid.

    The system prompt and the diff are never touched: those are the task.
    """
    if _history_chars(messages) <= budget:
        return messages

    trimmed = [dict(m) for m in messages]
    for message in trimmed:
        if _history_chars(trimmed) <= budget:
            break
        if message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        if len(content) <= 200:
            continue
        message["content"] = (
            content[:200] + f"... (trimmed, {len(content) - 200} characters of this result dropped)"
        )
    return trimmed


def _short_args(arguments: dict[str, Any], limit: int = 60) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    return text if len(text) <= limit else text[:limit] + "..."


def _parse_review(text: str | None) -> ReviewResult:
    """
    Models wrap JSON in prose or code fences often enough that being strict
    here would throw away good reviews over formatting.
    """
    if not text:
        return ReviewResult(summary="The model returned an empty response.")

    payload = _extract_json_object(text)
    if payload is None:
        # Not JSON at all: keep the prose rather than losing the review.
        return ReviewResult(summary=text.strip()[:2000])

    findings: list[Finding] = []
    for raw in payload.get("findings", []) or []:
        if not isinstance(raw, dict):
            continue
        findings.append(
            Finding(
                severity=str(raw.get("severity", "info")).lower(),
                title=str(raw.get("title", "Untitled finding")),
                body=str(raw.get("body", "")),
                file=raw.get("file") or None,
                line=raw.get("line") if isinstance(raw.get("line"), int) else None,
                evidence=raw.get("evidence") or None,
            )
        )

    return ReviewResult(summary=str(payload.get("summary", "")).strip(), findings=findings)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.rsplit("```", 1)[0]

    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost {...} span in the text.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
