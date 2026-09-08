from dataclasses import dataclass

from app.indexing.languages import LanguageAdapter, adapter_for_path


@dataclass
class ExtractedSymbol:
    name: str
    symbol_type: str  # "function" or "class"
    start_line: int
    end_line: int
    source: str


@dataclass
class ExtractedCall:
    name: str
    line: int  # used to attribute the call to its enclosing function/class


@dataclass
class ExtractedFile:
    language: str
    symbols: list[ExtractedSymbol]
    calls: list[ExtractedCall]
    # Identifier uses that are not calls: passing a function as an argument,
    # naming a type, referencing a class. Same shape as calls so both can be
    # attributed to their enclosing symbol the same way.
    references: list[ExtractedCall]


def parse_file(path: str, source: bytes) -> ExtractedFile | None:
    """
    Runs the right language's Tree-sitter queries over one file's contents.
    Returns None for files with no matching adapter (an unsupported
    language, or a non-code file), the caller just skips those.
    """
    adapter = adapter_for_path(path)
    if adapter is None:
        return None

    tree = adapter.parser().parse(source)
    symbols = _extract_symbols(adapter, source, tree.root_node)
    calls = _extract_calls(adapter, tree.root_node)
    references = _extract_references(adapter, tree.root_node, calls)
    return ExtractedFile(
        language=adapter.name, symbols=symbols, calls=calls, references=references
    )


def _extract_symbols(adapter: LanguageAdapter, source: bytes, root_node) -> list[ExtractedSymbol]:
    symbols: list[ExtractedSymbol] = []
    for symbol_type, query in (("function", adapter.function_query), ("class", adapter.class_query)):
        captures = query.captures(root_node)
        def_nodes = captures.get(f"{symbol_type}.def", [])
        name_nodes = captures.get(f"{symbol_type}.name", [])
        # Queries capture the definition node and its name node as siblings
        # of the same match; the simplest reliable way to pair them back up
        # is by position, since a name always falls inside its own def node.
        for name_node in name_nodes:
            enclosing = next(
                (d for d in def_nodes if d.start_byte <= name_node.start_byte and d.end_byte >= name_node.end_byte),
                None,
            )
            if enclosing is None:
                continue
            symbols.append(
                ExtractedSymbol(
                    name=name_node.text.decode("utf-8", errors="replace"),
                    symbol_type=symbol_type,
                    start_line=enclosing.start_point[0] + 1,
                    end_line=enclosing.end_point[0] + 1,
                    source=source[enclosing.start_byte : enclosing.end_byte].decode(
                        "utf-8", errors="replace"
                    ),
                )
            )
    return symbols


def _extract_references(
    adapter: LanguageAdapter, root_node, calls: list[ExtractedCall]
) -> list[ExtractedCall]:
    """
    Every identifier use, minus the ones already recorded as calls so the
    same site is not counted twice. Names that do not correspond to a symbol
    defined in the repository are dropped later, during indexing, which is
    where the set of known symbol names actually lives.
    """
    captures = adapter.reference_query.captures(root_node)
    call_sites = {(c.name, c.line) for c in calls}

    references: list[ExtractedCall] = []
    for node in captures.get("ref.name", []):
        name = node.text.decode("utf-8", errors="replace")
        line = node.start_point[0] + 1
        if (name, line) in call_sites:
            continue
        references.append(ExtractedCall(name=name, line=line))
    return references


def _extract_calls(adapter: LanguageAdapter, root_node) -> list[ExtractedCall]:
    captures = adapter.call_query.captures(root_node)
    return [
        ExtractedCall(
            name=node.text.decode("utf-8", errors="replace"),
            line=node.start_point[0] + 1,
        )
        for node in captures.get("call.name", [])
    ]
