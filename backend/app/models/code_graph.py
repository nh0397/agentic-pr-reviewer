import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

"""
These tables are the persisted form of the repository knowledge layer
(metadata + dependency graph). They are created in Phase 1 as schema, since
the review agent depends on them existing, but they are populated by the
indexing pipeline in Phase 2, not by anything in this phase.

The graph itself (function A calls function B) is stored as plain rows here,
not in NetworkX, because NetworkX only holds a graph in memory. Storing edges
in Postgres makes the graph durable across restarts; a NetworkX graph is
rebuilt from these rows on demand when the agent needs to traverse it.
"""


class SymbolType(str, enum.Enum):
    FUNCTION = "function"
    CLASS = "class"


class CodeFile(Base):
    __tablename__ = "code_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="python")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodeSymbol(Base):
    """A single function or class extracted from a file."""

    __tablename__ = "code_symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("code_files.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol_type: Mapped[SymbolType] = mapped_column(Enum(SymbolType), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)

    # Foreign key into Qdrant, not a SQL join. The embedding vector itself
    # lives in Qdrant; Postgres only needs to know which point represents it.
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SymbolCall(Base):
    """An edge in the dependency graph: caller_id's code calls callee_id."""

    __tablename__ = "symbol_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    caller_id: Mapped[int] = mapped_column(ForeignKey("code_symbols.id"), nullable=False)
    callee_id: Mapped[int] = mapped_column(ForeignKey("code_symbols.id"), nullable=False)
