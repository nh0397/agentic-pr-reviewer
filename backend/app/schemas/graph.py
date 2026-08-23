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
