"""
Bridges the model's tool calls to the real functions in app.tools.

Two jobs: describe each tool in the JSON schema the model expects, and
dispatch a call back to the plain Python function, converting the result to
something small enough to hand back as a message.
"""

import json
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.tools import code_tools

logger = logging.getLogger("agent.tools")

# Descriptions matter more than usual here: they are the only thing telling
# the model when a tool is worth reaching for, so each says what question it
# answers rather than just what it returns.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Search the repository for code semantically similar to a description "
                "or snippet. Use it to find precedent and conventions, for example "
                "'how are database errors handled' or 'existing permission checks'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Plain-English description of the code you want to find.",
                    },
                    "limit": {"type": "integer", "description": "Max results, default 8."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "description": (
                "Look up a function or class by its exact name to get its id, file and "
                "line range. Call this first to get an id for find_callers, find_callees "
                "or read_symbol. May return several matches if the name is not unique."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_callers",
            "description": (
                "Find everything that uses a symbol, by its id. This is the blast-radius "
                "question: use it before concluding a change to a function or class is "
                "safe. Results are marked 'call' (invoked) or 'reference' (passed as an "
                "argument, used as a type); both are real dependencies."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol_id": {"type": "integer"}},
                "required": ["symbol_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_callees",
            "description": "Find what a symbol depends on, by its id.",
            "parameters": {
                "type": "object",
                "properties": {"symbol_id": {"type": "integer"}},
                "required": ["symbol_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_symbol",
            "description": (
                "Read the full source of a symbol by its id, obtained from find_symbol "
                "or search_code. Use it when the diff alone does not show enough "
                "surrounding context to judge a change. To read an arbitrary file or "
                "line range instead, use read_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol_id": {"type": "integer"}},
                "required": ["symbol_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file by path, optionally a line range. Use this when you want "
                "code that is not a single indexed symbol, such as module-level setup, "
                "imports, or configuration. Output is line-numbered."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository-relative path, e.g. backend/app/auth.py",
                    },
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
]

# Tool results go back into the prompt, so an unbounded result would eat the
# context window a few calls in.
MAX_RESULT_ITEMS = 8
MAX_SOURCE_CHARS = 2500

# How many times one tool may fail before it is refused for the rest of the
# review. Counts consecutive failures; a success resets it.
MAX_TOOL_FAILURES = 2


class ToolExecutor:
    """Runs one tool call. Bound to a single repository and review so the
    model cannot reach outside the repository under review."""

    def __init__(self, repository_id: int, db: Session, source=None):
        self.repository_id = repository_id
        self.db = db
        # A RepositorySource, or None when no checkout is available; the read
        # tools degrade to saying so rather than failing the review.
        self.source = source
        # Kept so a finding can cite what evidence it was based on.
        self.calls_made: list[dict[str, Any]] = []
        self._failures: dict[str, int] = {}
        self._seen: dict[str, str] = {}

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        # Identical repeat calls are common once history trimming drops an
        # earlier result: the model forgets it already looked and asks again,
        # spending a step and a rate-limit window on nothing. Answer from the
        # first result and say so.
        signature = json.dumps({"tool": name, "args": arguments}, sort_keys=True, default=str)
        if signature in self._seen:
            logger.info("repeat call to %s, answering from the earlier result", name)
            return self._seen[signature]

        # A tool that keeps failing for an environmental reason (the vector
        # store being unreachable, say) will otherwise absorb the whole step
        # budget as the model patiently retries it with new phrasings.
        if self._failures.get(name, 0) >= MAX_TOOL_FAILURES:
            return json.dumps(
                {
                    "error": (
                        f"{name} is unavailable in this run and has stopped being retried. "
                        "Continue with the other tools."
                    )
                }
            )

        try:
            result = self._dispatch(name, arguments)
            if isinstance(result, dict) and "error" in result:
                self._failures[name] = self._failures.get(name, 0) + 1
            else:
                self._failures.pop(name, None)
        except Exception as exc:
            # Returned to the model rather than raised: a bad argument should
            # let it correct itself, not abort the review.
            logger.warning("tool %s failed: %s", name, exc)
            self._failures[name] = self._failures.get(name, 0) + 1
            result = {"error": f"{type(exc).__name__}: {exc}"}

        self.calls_made.append({"tool": name, "arguments": arguments, "result": result})
        payload = json.dumps(result, default=str)
        self._seen[signature] = payload
        return payload

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "search_code":
            query = arguments.get("query")
            if not query:
                return {"error": "query is required"}
            limit = min(int(arguments.get("limit", MAX_RESULT_ITEMS)), MAX_RESULT_ITEMS)
            hits = code_tools.search_code(self.repository_id, query, self.db, limit=limit)
            return [
                {
                    "symbol_id": h.id,
                    "name": h.name,
                    "type": h.symbol_type,
                    "path": h.path,
                    "lines": f"{h.start_line}-{h.end_line}",
                    "score": round(h.score, 3),
                }
                for h in hits
            ]

        if name == "find_symbol":
            symbol_name = arguments.get("name")
            if not symbol_name:
                return {"error": "name is required"}
            matches = code_tools.find_symbol(self.repository_id, symbol_name, self.db)
            if not matches:
                return {"result": f"No symbol named {symbol_name!r} is defined in this repository."}
            return [
                {
                    "symbol_id": m.id,
                    "name": m.name,
                    "type": m.symbol_type,
                    "path": m.path,
                    "lines": f"{m.start_line}-{m.end_line}",
                }
                for m in matches[:MAX_RESULT_ITEMS]
            ]

        if name in ("find_callers", "find_callees"):
            symbol_id = arguments.get("symbol_id")
            if symbol_id is None:
                return {"error": "symbol_id is required; use find_symbol to get one"}
            fn = code_tools.find_callers if name == "find_callers" else code_tools.find_callees
            relations = fn(int(symbol_id), self.db, limit=MAX_RESULT_ITEMS)
            if not relations:
                direction = "uses" if name == "find_callers" else "is used by"
                return {"result": f"Nothing {direction} this symbol within the repository."}
            return [
                {
                    "name": r.symbol.name,
                    "type": r.symbol.symbol_type,
                    "path": r.symbol.path,
                    "line": r.symbol.start_line,
                    "relationship": r.kind,
                }
                for r in relations
            ]

        if name == "read_symbol":
            symbol_id = arguments.get("symbol_id")
            if symbol_id is None:
                # The model sometimes reaches for read_symbol when it means
                # read_file; say so rather than just rejecting the call.
                if arguments.get("path"):
                    return {
                        "error": "read_symbol takes a symbol_id. To read by path, call read_file."
                    }
                return {"error": "symbol_id is required; use find_symbol to get one"}

            lookup = self.source.read_lines if self.source else None
            found = code_tools.read_symbol(int(symbol_id), self.db, lookup)
            if found is None:
                return {"error": f"No symbol with id {symbol_id}"}
            return {
                "name": found.name,
                "path": found.path,
                "lines": f"{found.start_line}-{found.end_line}",
                "source": found.source[:MAX_SOURCE_CHARS] or "(source unavailable)",
            }

        if name == "read_file":
            path = arguments.get("path")
            if not path:
                return {"error": "path is required"}
            if self.source is None:
                return {"error": "No checkout is available for this review."}
            text = self.source.read_lines(
                path, arguments.get("start_line"), arguments.get("end_line")
            )
            if text is None:
                return {"error": f"Could not read {path!r}. Check the path from a tool result."}
            return {"path": path, "content": text[:MAX_SOURCE_CHARS]}

        return {"error": f"Unknown tool {name!r}"}
