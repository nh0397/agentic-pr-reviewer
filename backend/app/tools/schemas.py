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
    # "call" means invoked; "reference" means used without being invoked,
    # e.g. passed as an argument or named as a type. Both matter for impact,
    # but the agent should be able to tell them apart when it reasons.
    kind: str
    # Where the relationship was observed, useful for the agent to cite.
    via_path: str
