"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type User = {
  id: number;
  username: string;
  avatar_url: string | null;
};

type Repository = {
  id: number;
  name: string;
  github_url: string;
  default_branch: string;
  index_status: string;
  created_at: string;
};

type GithubRepo = {
  name: string;
  full_name: string;
  html_url: string;
  default_branch: string;
  private: boolean;
};

// Every call needs this so the session cookie set at login actually gets
// sent, the frontend (port 3000) and backend (port 8000) are different
// origins as far as the browser's cookie rules are concerned.
const fetchOpts: RequestInit = { credentials: "include" };

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);

  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [githubRepos, setGithubRepos] = useState<GithubRepo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connectingRepo, setConnectingRepo] = useState<string | null>(null);
  const [backendUnreachable, setBackendUnreachable] = useState(false);

  async function loadSession() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, fetchOpts);
      setUser(res.ok ? await res.json() : null);
      setBackendUnreachable(false);
    } catch {
      setBackendUnreachable(true);
    } finally {
      setCheckingSession(false);
    }
  }

  async function loadRepositories() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories`, fetchOpts);
      if (res.ok) setRepositories(await res.json());
    } catch {
      setBackendUnreachable(true);
    }
  }

  async function loadGithubRepos() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/github/repos`, fetchOpts);
      if (res.ok) setGithubRepos(await res.json());
    } catch {
      setBackendUnreachable(true);
    }
  }

  useEffect(() => {
    loadSession();
  }, []);

  useEffect(() => {
    if (user) {
      loadRepositories();
      loadGithubRepos();
    }
  }, [user]);

  async function connectRepo(repo: GithubRepo) {
    setConnectingRepo(repo.full_name);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories`, {
        ...fetchOpts,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: repo.full_name,
          github_url: repo.html_url,
          default_branch: repo.default_branch,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Backend responded with ${res.status}`);
      }
      await loadRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect repository");
    } finally {
      setConnectingRepo(null);
    }
  }

  async function logout() {
    await fetch(`${API_BASE_URL}/api/auth/logout`, { ...fetchOpts, method: "POST" });
    setUser(null);
    setRepositories([]);
    setGithubRepos([]);
  }

  const connectedUrls = new Set(repositories.map((r) => r.github_url));

  if (!user) {
    return (
      <LandingPage
        checkingSession={checkingSession}
        backendUnreachable={backendUnreachable}
        apiBaseUrl={API_BASE_URL}
      />
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-2xl px-6 py-16">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
              Agentic PR Reviewer
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              Log in with GitHub, then connect a repository to review.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {user.avatar_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={user.avatar_url} alt={user.username} className="h-8 w-8 rounded-full" />
            )}
            <button onClick={logout} className="text-sm text-zinc-500 hover:underline">
              Log out
            </button>
          </div>
        </div>

        {backendUnreachable && (
          <p className="mt-6 rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Could not reach the backend at {API_BASE_URL}. Make sure it is running
            (<code>docker compose up -d --build</code> from the project root).
          </p>
        )}

        {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

        <div className="mt-10">
          <h2 className="text-lg font-medium text-black dark:text-zinc-50">
            Connected repositories
          </h2>
          {repositories.length === 0 ? (
            <p className="mt-2 text-zinc-500">None connected yet, pick one below.</p>
          ) : (
            <ul className="mt-4 flex flex-col gap-2">
              {repositories.map((repo) => (
                <li
                  key={repo.id}
                  className="rounded border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <p className="font-medium text-black dark:text-zinc-50">{repo.name}</p>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">
                    {repo.index_status}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-10">
          <h2 className="text-lg font-medium text-black dark:text-zinc-50">
            Your GitHub repositories
          </h2>
          <ul className="mt-4 flex flex-col gap-2">
            {githubRepos.map((repo) => {
              const connected = connectedUrls.has(repo.html_url);
              return (
                <li
                  key={repo.full_name}
                  className="flex items-center justify-between rounded border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <div>
                    <p className="font-medium text-black dark:text-zinc-50">{repo.full_name}</p>
                    <p className="text-xs text-zinc-400">{repo.private ? "private" : "public"}</p>
                  </div>
                  <button
                    disabled={connected || connectingRepo === repo.full_name}
                    onClick={() => connectRepo(repo)}
                    className="rounded border border-zinc-300 px-3 py-1 text-sm text-black disabled:opacity-50 dark:border-zinc-700 dark:text-white"
                  >
                    {connected
                      ? "Connected"
                      : connectingRepo === repo.full_name
                        ? "Connecting..."
                        : "Connect"}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </main>
    </div>
  );
}

function LandingPage({
  checkingSession,
  backendUnreachable,
  apiBaseUrl,
}: {
  checkingSession: boolean;
  backendUnreachable: boolean;
  apiBaseUrl: string;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-10">
      {/* Left, 70%: title and the graph animation */}
      <div className="relative flex flex-col justify-center overflow-hidden bg-zinc-50 px-10 py-20 dark:bg-black lg:col-span-7 lg:px-20">
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <DependencyGraphAnimation />
        </div>
        <div className="relative z-10 max-w-xl">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-500">
            Agentic Code Review
          </p>
          <h1 className="mt-4 text-5xl font-semibold tracking-tight text-black dark:text-white">
            Agentic GitHub
            <br />
            PR Reviewer
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
            An AI reviewer that investigates your codebase before it writes a single
            comment: tool calling, dependency graphs, and semantic search, not a diff
            pasted into a prompt.
          </p>
        </div>
      </div>

      {/* Right, 30%: login */}
      <div className="flex items-center justify-center border-t border-zinc-200 bg-white px-10 py-20 dark:border-zinc-800 dark:bg-zinc-950 lg:col-span-3 lg:border-l lg:border-t-0">
        <div className="w-full max-w-xs">
          <h2 className="text-xl font-semibold text-black dark:text-white">Welcome</h2>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Log in with GitHub to connect a repository.
          </p>

          {backendUnreachable && (
            <p className="mt-6 rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              Could not reach the backend at {apiBaseUrl}. Make sure it is running.
            </p>
          )}

          {checkingSession ? (
            <p className="mt-8 text-sm text-zinc-500">Checking session...</p>
          ) : (
            <a
              href={`${apiBaseUrl}/api/auth/github/login`}
              className="mt-8 flex items-center justify-center gap-2 rounded-lg bg-black px-4 py-3 font-medium text-white transition hover:opacity-90 dark:bg-white dark:text-black"
            >
              <GithubMark className="h-5 w-5" />
              Continue with GitHub
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

/**
 * A small dependency graph, gently pulsing and with signal flowing along
 * the edges. Nodes represent code (functions/classes), edges represent
 * calls, this is a literal picture of what the agent actually traverses.
 */
function DependencyGraphAnimation() {
  const nodes = [
    { id: "pr", x: 300, y: 300, r: 14, accent: true },
    { id: "a", x: 140, y: 160, r: 9 },
    { id: "b", x: 460, y: 150, r: 9 },
    { id: "c", x: 130, y: 440, r: 9 },
    { id: "d", x: 470, y: 450, r: 9 },
    { id: "e", x: 300, y: 90, r: 7 },
    { id: "f", x: 300, y: 520, r: 7 },
  ];
  const edges: [string, string][] = [
    ["pr", "a"],
    ["pr", "b"],
    ["pr", "c"],
    ["pr", "d"],
    ["a", "e"],
    ["b", "e"],
    ["c", "f"],
    ["d", "f"],
    ["a", "c"],
    ["b", "d"],
  ];
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return (
    <svg
      viewBox="0 0 600 600"
      className="h-[110%] w-[110%] max-w-none opacity-70 dark:opacity-60"
      aria-hidden="true"
    >
      <style>{`
        .pr-graph-edge {
          stroke: currentColor;
          stroke-width: 1.5;
          stroke-dasharray: 6 8;
          opacity: 0.35;
          animation: pr-graph-flow 6s linear infinite;
        }
        .pr-graph-node {
          fill: currentColor;
          transform-origin: center;
          transform-box: fill-box;
          animation: pr-graph-pulse 3.2s ease-in-out infinite;
        }
        .pr-graph-node-accent {
          fill: #6366f1;
          transform-origin: center;
          transform-box: fill-box;
          animation: pr-graph-pulse-accent 2.4s ease-in-out infinite;
        }
        @keyframes pr-graph-flow {
          to { stroke-dashoffset: -140; }
        }
        @keyframes pr-graph-pulse {
          0%, 100% { opacity: 0.55; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.25); }
        }
        @keyframes pr-graph-pulse-accent {
          0%, 100% { opacity: 0.85; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.15); }
        }
      `}</style>
      <g className="text-zinc-400 dark:text-zinc-600">
        {edges.map(([from, to], i) => (
          <line
            key={i}
            className="pr-graph-edge"
            x1={byId[from].x}
            y1={byId[from].y}
            x2={byId[to].x}
            y2={byId[to].y}
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </g>
      <g className="text-zinc-500 dark:text-zinc-400">
        {nodes.map((n, i) =>
          n.accent ? (
            <circle
              key={n.id}
              className="pr-graph-node-accent"
              cx={n.x}
              cy={n.y}
              r={n.r}
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ) : (
            <circle
              key={n.id}
              className="pr-graph-node"
              cx={n.x}
              cy={n.y}
              r={n.r}
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          )
        )}
      </g>
    </svg>
  );
}
