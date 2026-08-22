"use client";

import { FormEvent, useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Repository = {
  id: number;
  name: string;
  github_url: string;
  default_branch: string;
  index_status: string;
  created_at: string;
};

export default function Home() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [name, setName] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadRepositories() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories`);
      if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
      setRepositories(await res.json());
      setError(null);
    } catch {
      setError("Could not reach the backend. Is it running on port 8000?");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRepositories();
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, github_url: githubUrl }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Backend responded with ${res.status}`);
      }
      setName("");
      setGithubUrl("");
      await loadRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add repository");
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Agentic PR Reviewer
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Phase 1: connect a repository. Indexing and review come later.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-3">
          <input
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
            placeholder="Repository name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            className="rounded border border-zinc-300 bg-white px-3 py-2 text-black dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
            placeholder="GitHub URL"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            required
          />
          <button
            type="submit"
            className="rounded bg-black px-4 py-2 font-medium text-white dark:bg-white dark:text-black"
          >
            Add repository
          </button>
        </form>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        <div className="mt-10">
          <h2 className="text-lg font-medium text-black dark:text-zinc-50">Repositories</h2>
          {loading ? (
            <p className="mt-2 text-zinc-500">Loading...</p>
          ) : repositories.length === 0 ? (
            <p className="mt-2 text-zinc-500">No repositories yet.</p>
          ) : (
            <ul className="mt-4 flex flex-col gap-2">
              {repositories.map((repo) => (
                <li
                  key={repo.id}
                  className="rounded border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <p className="font-medium text-black dark:text-zinc-50">{repo.name}</p>
                  <p className="text-sm text-zinc-500">{repo.github_url}</p>
                  <p className="text-xs uppercase tracking-wide text-zinc-400">
                    {repo.index_status}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
