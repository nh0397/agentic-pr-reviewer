from pydantic import BaseModel


class LanguageBreakdown(BaseModel):
    language: str
    files: int


class GraphStats(BaseModel):
    files: int
    symbols: int
    functions: int
    classes: int
    edges: int
    languages: list[LanguageBreakdown]


class GraphNode(BaseModel):
    id: int
    name: str
    symbol_type: str
    path: str


class GraphEdge(BaseModel):
    source: int
    target: int


class RepositoryGraph(BaseModel):
    stats: GraphStats
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class IndexJobRead(BaseModel):
    id: int
    repository_id: int
    status: str
    # 0 while running or next in line, higher the further back it is.
    queue_position: int
    phase: str | None = None
    detail: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    error: str | None = None
    files_indexed: int | None = None
    symbols_found: int | None = None
    calls_found: int | None = None
