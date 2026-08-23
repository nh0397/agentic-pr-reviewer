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
class ExtractedFile:
    language: str
    symbols: list[ExtractedSymbol]
    call_names: list[str]  # every name called anywhere in the file


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
    call_names = _extract_call_names(adapter, tree.root_node)
    return ExtractedFile(language=adapter.name, symbols=symbols, call_names=call_names)


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


def _extract_call_names(adapter: LanguageAdapter, root_node) -> list[str]:
    captures = adapter.call_query.captures(root_node)
    return [node.text.decode("utf-8", errors="replace") for node in captures.get("call.name", [])]
