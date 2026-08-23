# Agentic GitHub PR Reviewer

An AI PR reviewer that investigates a pull request using tools (code search,
dependency graph queries, semantic similarity) before writing a review,
instead of sending the raw diff straight to a model.

## Phase 1 scope

This phase proves the base of the system: a repository can be registered
through the frontend, stored in Postgres, and read back through the API.
Indexing, embeddings, and the review agent come once this foundation is
confirmed to work.

## Architecture

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js | Fast iteration, deploys cleanly to Vercel |
| Backend | FastAPI | Runs as a long lived process rather than a serverless function, since repository indexing can take longer than a serverless timeout allows |
| Database | Postgres | Holds repository metadata, dependency graph edges, and review history; a relational model fits this structured data well |
| Vector store | Qdrant | Purpose built for approximate nearest neighbor search over function and class embeddings |
| Embeddings | `sentence-transformers`, run in-process | Keeps indexing self-contained, no external inference dependency in the critical path |
| LLM | Groq, behind an `LLMClient` interface | Fast inference on open-weight models with an OpenAI-compatible API; the interface means swapping providers later is a config change, not a rewrite |
| Graph | NetworkX, built from rows in Postgres | Postgres is the durable source of truth for edges; NetworkX handles traversal in memory at query time |
| Parsing | Tree-sitter, Python first | Proves the pipeline end to end before extending to additional languages |

Every external service is read from an environment variable, never
hardcoded, so the same code runs unchanged against local containers or
managed cloud services.

## Running locally

Requires Docker and Node 18+ for the frontend (built against Node 20).

Docker runs the infrastructure only (Postgres and Qdrant). The backend
runs locally, so code changes reload instantly with no image rebuild.

**1. Infrastructure** (needs Docker Desktop running):

```bash
docker compose up -d
```

**2. Backend** (first time: create the venv and install first):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

After the first time, only the last two lines are needed. If Postgres
is not running, the backend exits immediately with a message saying so
rather than failing on every request.

**3. Frontend**, in a separate terminal:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Running the backend in Docker instead

Mirrors how it is deployed, and is the slower path since it rebuilds the
image. Not needed for day to day development.

```bash
docker compose --profile full up -d --build
```

## Not built yet

- Repository indexing (Tree-sitter parsing, embeddings, graph population)
- The review agent and its tools
- GitHub OAuth (a single demo flow with a manually provided repo URL and
  token is used for now, since OAuth is orthogonal to the agentic
  reasoning this project is meant to demonstrate)
- Background job processing for indexing (a synchronous endpoint is used
  for now; moving to a task queue is a deliberate later step once the
  indexing logic itself is proven)
