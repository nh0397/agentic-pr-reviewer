from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.indexing.embeddings import embed_texts
from app.indexing.git import cloned_repo, walk_source_files
from app.indexing.parser import parse_file
from app.indexing.vector_store import delete_repository_vectors, upsert_symbol_vectors
from app.models.code_graph import CodeFile, CodeSymbol, SymbolCall, SymbolType
from app.models.repository import Repository


@dataclass
class IndexResult:
    files_indexed: int
    symbols_found: int
    calls_found: int


def index_repository(repository: Repository, access_token: str | None, db: Session) -> IndexResult:
    _clear_existing_index(repository.id, db)

    # Accumulated across every file in the repo, not reset per file, so a
    # call in one file can resolve to a function defined in another. This is
    # name-based only, not import- or scope-aware: two unrelated functions
    # sharing a name will incorrectly link. That's a real limitation, full
    # resolution would need type/import analysis, out of scope for now.
    name_to_symbol_id: dict[str, int] = {}
    pending_calls: list[tuple[int, list[str]]] = []
    embedding_texts: list[str] = []
    embedding_symbol_ids: list[int] = []
    files_indexed = 0

    with cloned_repo(repository.github_url, access_token) as repo_path:
        for path in walk_source_files(repo_path):
            try:
                source = path.read_bytes()
            except OSError:
                continue

            relative_path = str(path.relative_to(repo_path))
            result = parse_file(relative_path, source)
            if result is None or not result.symbols:
                continue

            code_file = CodeFile(repository_id=repository.id, path=relative_path, language=result.language)
            db.add(code_file)
            db.flush()  # need code_file.id before creating its symbols
            files_indexed += 1

            file_symbol_ids: list[int] = []
            for symbol in result.symbols:
                row = CodeSymbol(
                    file_id=code_file.id,
                    name=symbol.name,
                    symbol_type=SymbolType(symbol.symbol_type),
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
                db.add(row)
                db.flush()  # need row.id for the name map and embedding link
                name_to_symbol_id.setdefault(symbol.name, row.id)
                file_symbol_ids.append(row.id)
                embedding_texts.append(symbol.source[:2000])
                embedding_symbol_ids.append(row.id)

            for symbol_id in file_symbol_ids:
                pending_calls.append((symbol_id, result.call_names))

    calls_found = 0
    for caller_id, call_names in pending_calls:
        for name in call_names:
            callee_id = name_to_symbol_id.get(name)
            if callee_id and callee_id != caller_id:
                db.add(SymbolCall(caller_id=caller_id, callee_id=callee_id))
                calls_found += 1

    db.commit()

    if embedding_texts:
        vectors = embed_texts(embedding_texts)
        points = [
            (symbol_id, vector, {"repository_id": repository.id, "symbol_id": symbol_id})
            for symbol_id, vector in zip(embedding_symbol_ids, vectors)
        ]
        upsert_symbol_vectors(points)

        for symbol_id in embedding_symbol_ids:
            db.query(CodeSymbol).filter(CodeSymbol.id == symbol_id).update(
                {"qdrant_point_id": str(symbol_id)}
            )
        db.commit()

    return IndexResult(
        files_indexed=files_indexed,
        symbols_found=len(embedding_symbol_ids),
        calls_found=calls_found,
    )


def _clear_existing_index(repository_id: int, db: Session) -> None:
    """Re-indexing (after new commits, or just retrying) should replace the
    old index, not append to it."""
    file_ids = [row[0] for row in db.query(CodeFile.id).filter(CodeFile.repository_id == repository_id).all()]
    if file_ids:
        symbol_ids = [
            row[0] for row in db.query(CodeSymbol.id).filter(CodeSymbol.file_id.in_(file_ids)).all()
        ]
        if symbol_ids:
            db.query(SymbolCall).filter(
                SymbolCall.caller_id.in_(symbol_ids) | SymbolCall.callee_id.in_(symbol_ids)
            ).delete(synchronize_session=False)
            db.query(CodeSymbol).filter(CodeSymbol.id.in_(symbol_ids)).delete(synchronize_session=False)
        db.query(CodeFile).filter(CodeFile.id.in_(file_ids)).delete(synchronize_session=False)
    db.commit()
    delete_repository_vectors(repository_id)
