from pydantic import BaseModel


class SymbolRef(BaseModel):
    """How every tool refers to a piece of code, so results from different
    tools can be cross-referenced by the agent."""

    id: int
    name: str
    symbol_type: str
    path: str
    start_line: int
    end_line: int


class SearchHit(SymbolRef):
    score: float


class SymbolSource(SymbolRef):
    source: str


class CallRelation(BaseModel):
    symbol: SymbolRef
    # Where the relationship was observed, useful for the agent to cite.
    via_path: str
