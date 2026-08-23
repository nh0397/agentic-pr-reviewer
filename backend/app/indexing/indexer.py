import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.indexing.embeddings import embed_texts
from app.indexing.git import cloned_repo, walk_source_files
from app.indexing.parser import parse_file
from app.indexing.vector_store import delete_repository_vectors, upsert_symbol_vectors
from app.models.code_graph import CodeFile, CodeSymbol, SymbolCall, SymbolType
from app.models.repository import Repository


logger = logging.getLogger("indexing")

# How often to report progress while walking files. Logging every file is
# unreadable on a large repository; this gives a steady heartbeat instead.
PROGRESS_EVERY_N_FILES = 25


@dataclass
class IndexResult:
    files_indexed: int
    symbols_found: int
    calls_found: int


def index_repository(repository: Repository, access_token: str | None, db: Session) -> IndexResult:
    started = time.monotonic()
    logger.info("[%s] clearing any previous index", repository.name)
    _clear_existing_index(repository.id, db)

    # Accumulated across every file in the repo, not reset per file, so a
    # call in one file can resolve to a function defined in another. This is
    # name-based only, not import- or scope-aware: two unrelated functions
    # sharing a name will incorrectly link. That's a real limitation, full
    # resolution would need type/import analysis, out of scope for now.
    name_to_symbol_id: dict[str, int] = {}
    pending_calls: list[tuple[int, str]] = []
    embedding_texts: list[str] = []
    embedding_symbol_ids: list[int] = []
    files_indexed = 0

    # Never log the authenticated clone URL; it carries the access token.
    logger.info("[%s] cloning %s", repository.name, repository.github_url)
    clone_started = time.monotonic()

    with cloned_repo(repository.github_url, access_token) as repo_path:
        logger.info(
            "[%s] cloned in %.1fs, walking files", repository.name, time.monotonic() - clone_started
        )
        parse_started = time.monotonic()
        files_seen = 0
        files_skipped = 0

        for path in walk_source_files(repo_path):
            files_seen += 1
            if files_seen % PROGRESS_EVERY_N_FILES == 0:
                logger.info(
                    "[%s] %d files scanned, %d indexed so far (%d symbols)",
                    repository.name,
                    files_seen,
                    files_indexed,
                    len(embedding_symbol_ids),
                )

            try:
                source = path.read_bytes()
            except OSError:
                files_skipped += 1
                continue

            relative_path = str(path.relative_to(repo_path))
            result = parse_file(relative_path, source)
            if result is None or not result.symbols:
                continue

            code_file = CodeFile(repository_id=repository.id, path=relative_path, language=result.language)
            db.add(code_file)
            db.flush()  # need code_file.id before creating its symbols
            files_indexed += 1

            # (symbol_id, start_line, end_line) for this file, used below to
            # work out which symbol each call sits inside.
            file_symbol_ranges: list[tuple[int, int, int]] = []
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
                file_symbol_ranges.append((row.id, symbol.start_line, symbol.end_line))
                embedding_texts.append(symbol.source[:2000])
                embedding_symbol_ids.append(row.id)

            for call in result.calls:
                caller_id = _innermost_symbol_at(file_symbol_ranges, call.line)
                if caller_id is not None:
                    pending_calls.append((caller_id, call.name))

    logger.info(
        "[%s] parsed %d/%d files in %.1fs: %d symbols, %d call sites%s",
        repository.name,
        files_indexed,
        files_seen,
        time.monotonic() - parse_started,
        len(embedding_symbol_ids),
        len(pending_calls),
        f", {files_skipped} unreadable" if files_skipped else "",
    )

    calls_found = 0
    unresolved = 0
    seen_edges: set[tuple[int, int]] = set()
    for caller_id, call_name in pending_calls:
        callee_id = name_to_symbol_id.get(call_name)
        if callee_id is None:
            # Almost always a library or builtin call, not something defined
            # in this repository, so there is nothing to draw an edge to.
            unresolved += 1
            continue
        if callee_id == caller_id:
            continue
        # A calls B ten times is still one edge in the graph.
        if (caller_id, callee_id) in seen_edges:
            continue
        seen_edges.add((caller_id, callee_id))
        db.add(SymbolCall(caller_id=caller_id, callee_id=callee_id))
        calls_found += 1

    db.commit()
    logger.info(
        "[%s] resolved %d call edges (%d call sites pointed outside this repository)",
        repository.name,
        calls_found,
        unresolved,
    )

    if embedding_texts:
        logger.info("[%s] embedding %d symbols...", repository.name, len(embedding_texts))
        embed_started = time.monotonic()
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
        logger.info(
            "[%s] embedded and stored %d vectors in %.1fs",
            repository.name,
            len(vectors),
            time.monotonic() - embed_started,
        )
    else:
        logger.info("[%s] no symbols found, nothing to embed", repository.name)

    logger.info(
        "[%s] finished in %.1fs: %d files, %d symbols, %d call edges",
        repository.name,
        time.monotonic() - started,
        files_indexed,
        len(embedding_symbol_ids),
        calls_found,
    )

    return IndexResult(
        files_indexed=files_indexed,
        symbols_found=len(embedding_symbol_ids),
        calls_found=calls_found,
    )


def _innermost_symbol_at(
    symbol_ranges: list[tuple[int, int, int]], line: int
) -> int | None:
    """
    Which symbol does this line belong to? A method inside a class sits
    inside both, so the narrowest range wins: a call in a method is the
    method's call, not the whole class's.
    """
    best_id: int | None = None
    best_span: int | None = None
    for symbol_id, start_line, end_line in symbol_ranges:
        if start_line <= line <= end_line:
            span = end_line - start_line
            if best_span is None or span < best_span:
                best_id, best_span = symbol_id, span
    return best_id


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
