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

  async function loadSession() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, fetchOpts);
      setUser(res.ok ? await res.json() : null);
    } finally {
      setCheckingSession(false);
    }
  }

  async function loadRepositories() {
    const res = await fetch(`${API_BASE_URL}/api/repositories`, fetchOpts);
    if (res.ok) setRepositories(await res.json());
  }

  async function loadGithubRepos() {
    const res = await fetch(`${API_BASE_URL}/api/github/repos`, fetchOpts);
    if (res.ok) setGithubRepos(await res.json());
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
          {user && (
            <div className="flex items-center gap-3">
              {user.avatar_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatar_url} alt={user.username} className="h-8 w-8 rounded-full" />
              )}
              <button onClick={logout} className="text-sm text-zinc-500 hover:underline">
                Log out
              </button>
            </div>
          )}
        </div>

        {checkingSession ? (
          <p className="mt-10 text-zinc-500">Checking session...</p>
        ) : !user ? (
          <a
            href={`${API_BASE_URL}/api/auth/github/login`}
            className="mt-10 inline-flex items-center rounded bg-black px-4 py-2 font-medium text-white dark:bg-white dark:text-black"
          >
            Log in with GitHub
          </a>
        ) : (
          <>
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
                        <p className="font-medium text-black dark:text-zinc-50">
                          {repo.full_name}
                        </p>
                        <p className="text-xs text-zinc-400">
                          {repo.private ? "private" : "public"}
                        </p>
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
          </>
        )}
      </main>
    </div>
  );
}
