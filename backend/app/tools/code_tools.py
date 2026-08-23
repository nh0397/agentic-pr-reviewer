"""
The tools the review agent calls to investigate a repository.

Each one is an ordinary function over the indexed knowledge layer, with no
LLM involved, so it can be tested and trusted on its own. The agent decides
which to call and when; these only answer questions.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.indexing.embeddings import embed_texts
from app.indexing.vector_store import COLLECTION_NAME, get_qdrant_client
from app.models.code_graph import CodeFile, CodeSymbol, SymbolCall
from app.tools.schemas import CallRelation, SearchHit, SymbolRef, SymbolSource

logger = logging.getLogger("tools")

DEFAULT_LIMIT = 10


def _to_ref(symbol: CodeSymbol, path: str) -> SymbolRef:
    return SymbolRef(
        id=symbol.id,
        name=symbol.name,
        symbol_type=symbol.symbol_type.value,
        path=path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
    )


def search_code(
    repository_id: int, query: str, db: Session, limit: int = DEFAULT_LIMIT
) -> list[SearchHit]:
    """
    Find code that is semantically similar to a plain-English description or
    a snippet. This is how the agent finds precedent: "how is authentication
    handled elsewhere in this repository?"
    """
    vector = embed_texts([query])[0]
    client = get_qdrant_client()

    from qdrant_client.http import models as qmodels

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="repository_id", match=qmodels.MatchValue(value=repository_id)
                )
            ]
        ),
    )

    hits: list[SearchHit] = []
    for point in response.points:
        symbol_id = point.payload.get("symbol_id") if point.payload else None
        if symbol_id is None:
            continue
        row = db.execute(
            select(CodeSymbol, CodeFile.path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(CodeSymbol.id == symbol_id)
        ).first()
        if row is None:
            # Vector store and database can drift if indexing was
            # interrupted; skip rather than fail the whole search.
            continue
        symbol, path = row
        hits.append(SearchHit(**_to_ref(symbol, path).model_dump(), score=point.score))

    logger.info("search_code(repo=%s, %r) -> %d hits", repository_id, query, len(hits))
    return hits


def find_symbol(
    repository_id: int, name: str, db: Session, limit: int = DEFAULT_LIMIT
) -> list[SymbolRef]:
    """Look a symbol up by exact name. Several files can define the same
    name, so this returns every match rather than guessing."""
    rows = db.execute(
        select(CodeSymbol, CodeFile.path)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.repository_id == repository_id, CodeSymbol.name == name)
        .limit(limit)
    ).all()
    return [_to_ref(symbol, path) for symbol, path in rows]


def find_callers(symbol_id: int, db: Session, limit: int = DEFAULT_LIMIT) -> list[CallRelation]:
    """
    Who calls this symbol. This is the blast-radius question: change a
    function's behaviour and these are the places that feel it.
    """
    caller = aliased(CodeSymbol)
    rows = db.execute(
        select(caller, CodeFile.path)
        .join(SymbolCall, SymbolCall.caller_id == caller.id)
        .join(CodeFile, caller.file_id == CodeFile.id)
        .where(SymbolCall.callee_id == symbol_id)
        .limit(limit)
    ).all()
    return [CallRelation(symbol=_to_ref(s, path), via_path=path) for s, path in rows]


def find_callees(symbol_id: int, db: Session, limit: int = DEFAULT_LIMIT) -> list[CallRelation]:
    """What this symbol depends on, i.e. what it could break against."""
    callee = aliased(CodeSymbol)
    rows = db.execute(
        select(callee, CodeFile.path)
        .join(SymbolCall, SymbolCall.callee_id == callee.id)
        .join(CodeFile, callee.file_id == CodeFile.id)
        .where(SymbolCall.caller_id == symbol_id)
        .limit(limit)
    ).all()
    return [CallRelation(symbol=_to_ref(s, path), via_path=path) for s, path in rows]


def read_symbol(symbol_id: int, db: Session, source_lookup=None) -> SymbolSource | None:
    """
    The actual source of one symbol. `source_lookup(path, start, end)` is
    supplied by the caller, since where the files live (a fresh clone, a
    cached checkout) is not this layer's concern.
    """
    row = db.execute(
        select(CodeSymbol, CodeFile.path)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeSymbol.id == symbol_id)
    ).first()
    if row is None:
        return None
    symbol, path = row

    source = ""
    if source_lookup is not None:
        source = source_lookup(path, symbol.start_line, symbol.end_line) or ""

    return SymbolSource(**_to_ref(symbol, path).model_dump(), source=source)
