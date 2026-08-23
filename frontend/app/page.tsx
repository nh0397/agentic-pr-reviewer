"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { API_BASE_URL, fetchOpts, useSession } from "./useSession";

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
  description: string | null;
  language: string | null;
  stargazers_count: number;
  updated_at: string;
};

export default function DashboardPage() {
  const { user, checkingSession, backendUnreachable: sessionUnreachable, logout } = useSession();
  const router = useRouter();

  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [githubRepos, setGithubRepos] = useState<GithubRepo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connectingRepo, setConnectingRepo] = useState<string | null>(null);
  const [dataUnreachable, setDataUnreachable] = useState(false);

  useEffect(() => {
    // Same rule as the login page: only redirect once we actually know
    // you're not logged in. A backend outage also leaves `user` null, but
    // that should show an error here, not send you bouncing to /login.
    if (!checkingSession && !user && !sessionUnreachable) {
      router.replace("/login");
    }
  }, [checkingSession, user, sessionUnreachable, router]);

  async function loadRepositories() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories`, fetchOpts);
      if (res.ok) setRepositories(await res.json());
    } catch {
      setDataUnreachable(true);
    }
  }

  async function loadGithubRepos() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/github/repos`, fetchOpts);
      if (res.ok) setGithubRepos(await res.json());
    } catch {
      setDataUnreachable(true);
    }
  }

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

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const backendUnreachable = sessionUnreachable || dataUnreachable;

  // Checking the session, or about to redirect: show a small neutral
  // loading state instead of any page content, so refreshing this route
  // never flashes the login screen before settling on the dashboard.
  if (checkingSession || (!user && !backendUnreachable)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-black">
        <p className="text-sm text-zinc-500">Loading...</p>
      </div>
    );
  }

  const connectedUrls = new Set(repositories.map((r) => r.github_url));

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <nav className="sticky top-0 z-10 border-b border-zinc-200 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-black/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-10">
          <span className="font-semibold text-black dark:text-zinc-50">Agentic PR Reviewer</span>
          <div className="flex items-center gap-3">
            {user?.avatar_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={user.avatar_url} alt={user.username} className="h-8 w-8 rounded-full" />
            )}
            {user && (
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{user.username}</span>
            )}
            <button onClick={handleLogout} className="text-sm text-zinc-500 hover:underline">
              Log out
            </button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-7xl px-6 py-10 lg:px-10">
        <p className="text-zinc-600 dark:text-zinc-400">
          Connect a repository from GitHub to review its pull requests.
        </p>

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
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {repositories.map((repo) => (
                <div
                  key={repo.id}
                  className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-medium text-black dark:text-zinc-50">
                      {repo.name}
                    </p>
                    <StatusPill status={repo.index_status} />
                  </div>
                  <p className="mt-1 text-xs text-zinc-400">
                    Default branch: {repo.default_branch}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-10">
          <h2 className="text-lg font-medium text-black dark:text-zinc-50">
            Your GitHub repositories
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {githubRepos.map((repo) => {
              const connected = connectedUrls.has(repo.html_url);
              return (
                <div
                  key={repo.full_name}
                  className="flex flex-col rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-medium text-black dark:text-zinc-50">
                      {repo.name}
                    </p>
                    <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                      {repo.private ? "Private" : "Public"}
                    </span>
                  </div>

                  <p className="mt-1 line-clamp-2 flex-1 text-sm text-zinc-500 dark:text-zinc-400">
                    {repo.description ?? "No description"}
                  </p>

                  <div className="mt-4 flex items-center justify-between">
                    <div className="flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                      {repo.language && (
                        <span className="flex items-center gap-1.5">
                          <span
                            className="h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: languageColor(repo.language) }}
                          />
                          {repo.language}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <StarIcon className="h-3.5 w-3.5" />
                        {repo.stargazers_count}
                      </span>
                      <span>{formatRelativeTime(repo.updated_at)}</span>
                    </div>

                    <button
                      disabled={connected || connectingRepo === repo.full_name}
                      onClick={() => connectRepo(repo)}
                      className="shrink-0 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium text-black transition disabled:opacity-50 dark:border-zinc-700 dark:text-white"
                    >
                      {connected
                        ? "Connected"
                        : connectingRepo === repo.full_name
                          ? "Connecting..."
                          : "Connect"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}

const STATUS_STYLES: Record<string, { label: string; className: string; pulse?: boolean }> = {
  not_indexed: {
    label: "Not indexed",
    className: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  },
  indexing: {
    label: "Indexing",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
    pulse: true,
  },
  indexed: {
    label: "Indexed",
    className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  },
  failed: {
    label: "Failed",
    className: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  },
};

function StatusPill({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.not_indexed;
  return (
    <span
      className={`flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full bg-current ${style.pulse ? "animate-pulse" : ""}`}
      />
      {style.label}
    </span>
  );
}

const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: "#3178c6",
  JavaScript: "#f1e05a",
  Python: "#3572A5",
  Go: "#00ADD8",
  Rust: "#dea584",
  Java: "#b07219",
  Ruby: "#701516",
  "C++": "#f34b7d",
  C: "#555555",
  HTML: "#e34c26",
  CSS: "#563d7c",
  Shell: "#89e051",
  PHP: "#4F5D95",
};

function languageColor(language: string): string {
  return LANGUAGE_COLORS[language] ?? "#8b8b8b";
}

function formatRelativeTime(dateString: string): string {
  const diffMs = new Date(dateString).getTime() - Date.now();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(diffDays) < 1) {
    const diffHours = Math.round(diffMs / (1000 * 60 * 60));
    return formatter.format(diffHours, "hour");
  }
  if (Math.abs(diffDays) < 30) return formatter.format(diffDays, "day");
  return formatter.format(Math.round(diffDays / 30), "month");
}

function StarIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.193L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z" />
    </svg>
  );
}
