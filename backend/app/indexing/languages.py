"""
One adapter per language: which file extensions it owns, and the Tree-sitter
queries that say what "a function," "a class," and "a call" look like in
that language's grammar. Adding a new language later means adding one more
entry here, the rest of the indexing pipeline never changes.
"""

from dataclasses import dataclass

import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser, Query


@dataclass(frozen=True)
class LanguageAdapter:
    name: str
    extensions: tuple[str, ...]
    language: Language
    function_query: Query
    class_query: Query
    call_query: Query
    # Bare identifier uses. A function is often handed to something rather
    # than called: `Depends(get_current_user)`, a JSX callback prop, a type
    # annotation. Those are real usages, and a "what breaks if I change
    # this?" answer that ignores them is worse than useless.
    reference_query: Query

    def parser(self) -> Parser:
        return Parser(self.language)


_PY_LANGUAGE = Language(tspython.language())
_JS_LANGUAGE = Language(tsjavascript.language())
_TS_LANGUAGE = Language(tstypescript.language_typescript())
_TSX_LANGUAGE = Language(tstypescript.language_tsx())

PYTHON = LanguageAdapter(
    name="python",
    extensions=(".py",),
    language=_PY_LANGUAGE,
    function_query=Query(
        _PY_LANGUAGE,
        "(function_definition name: (identifier) @function.name) @function.def",
    ),
    class_query=Query(
        _PY_LANGUAGE,
        "(class_definition name: (identifier) @class.name) @class.def",
    ),
    call_query=Query(
        _PY_LANGUAGE,
        """
        (call function: (identifier) @call.name)
        (call function: (attribute attribute: (identifier) @call.name))
        """,
    ),
    reference_query=Query(_PY_LANGUAGE, "(identifier) @ref.name"),
)

# JavaScript and TypeScript share almost all of their relevant grammar node
# names (TypeScript's grammar is a superset), so the same queries work for
# both, just against a different compiled language.
_JS_STYLE_FUNCTION_QUERY = """
(function_declaration name: (identifier) @function.name) @function.def
(method_definition name: (property_identifier) @function.name) @function.def
(variable_declarator
  name: (identifier) @function.name
  value: [(arrow_function) (function_expression)]) @function.def
"""
_JS_STYLE_CLASS_QUERY = "(class_declaration name: (_) @class.name) @class.def"
_JS_STYLE_CALL_QUERY = """
(call_expression function: (identifier) @call.name)
(call_expression function: (member_expression property: (property_identifier) @call.name))
"""
# Plain JavaScript has no `type_identifier` node; only the TypeScript
# grammar does, so the two need separate reference queries.
_JS_REFERENCE_QUERY = "(identifier) @ref.name"
_TS_REFERENCE_QUERY = """
(identifier) @ref.name
(type_identifier) @ref.name
"""

JAVASCRIPT = LanguageAdapter(
    name="javascript",
    extensions=(".js", ".jsx", ".mjs", ".cjs"),
    language=_JS_LANGUAGE,
    function_query=Query(_JS_LANGUAGE, _JS_STYLE_FUNCTION_QUERY),
    class_query=Query(_JS_LANGUAGE, _JS_STYLE_CLASS_QUERY),
    call_query=Query(_JS_LANGUAGE, _JS_STYLE_CALL_QUERY),
    reference_query=Query(_JS_LANGUAGE, _JS_REFERENCE_QUERY),
)

TYPESCRIPT = LanguageAdapter(
    name="typescript",
    extensions=(".ts",),
    language=_TS_LANGUAGE,
    function_query=Query(_TS_LANGUAGE, _JS_STYLE_FUNCTION_QUERY),
    class_query=Query(_TS_LANGUAGE, _JS_STYLE_CLASS_QUERY),
    call_query=Query(_TS_LANGUAGE, _JS_STYLE_CALL_QUERY),
    reference_query=Query(_TS_LANGUAGE, _TS_REFERENCE_QUERY),
)

TSX = LanguageAdapter(
    name="tsx",
    extensions=(".tsx",),
    language=_TSX_LANGUAGE,
    function_query=Query(_TSX_LANGUAGE, _JS_STYLE_FUNCTION_QUERY),
    class_query=Query(_TSX_LANGUAGE, _JS_STYLE_CLASS_QUERY),
    call_query=Query(_TSX_LANGUAGE, _JS_STYLE_CALL_QUERY),
    reference_query=Query(_TSX_LANGUAGE, _TS_REFERENCE_QUERY),
)

ADAPTERS: tuple[LanguageAdapter, ...] = (PYTHON, JAVASCRIPT, TYPESCRIPT, TSX)

_EXTENSION_TO_ADAPTER = {ext: adapter for adapter in ADAPTERS for ext in adapter.extensions}


def adapter_for_path(path: str) -> LanguageAdapter | None:
    for ext, adapter in _EXTENSION_TO_ADAPTER.items():
        if path.endswith(ext):
            return adapter
    return None
