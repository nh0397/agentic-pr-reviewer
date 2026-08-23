"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { API_BASE_URL, fetchOpts, useSession } from "../../useSession";
import { DependencyGraph, type GraphEdge, type GraphNode } from "../../DependencyGraph";

type LanguageBreakdown = { language: string; files: number };

type RepositoryGraph = {
  stats: {
    files: number;
    symbols: number;
    functions: number;
    classes: number;
    edges: number;
    languages: LanguageBreakdown[];
  };
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type Repository = {
  id: number;
  name: string;
  github_url: string;
  default_branch: string;
  index_status: string;
};

export default function RepositoryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { user, checkingSession, backendUnreachable } = useSession();
  const router = useRouter();

  const [repository, setRepository] = useState<Repository | null>(null);
  const [graph, setGraph] = useState<RepositoryGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!checkingSession && !user && !backendUnreachable) {
      router.replace("/login");
    }
  }, [checkingSession, user, backendUnreachable, router]);

  const load = useCallback(async () => {
    try {
      const [repoRes, graphRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/repositories/${id}`, fetchOpts),
        fetch(`${API_BASE_URL}/api/repositories/${id}/graph`, fetchOpts),
      ]);
      if (repoRes.ok) setRepository(await repoRes.json());
      if (graphRes.ok) setGraph(await graphRes.json());
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function reindex() {
    setIndexing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/repositories/${id}/index`, {
        ...fetchOpts,
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Backend responded with ${res.status}`);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Indexing failed");
    } finally {
      setIndexing(false);
    }
  }

  if (checkingSession || (loading && user)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-black">
        <p className="text-sm text-zinc-500">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <nav className="sticky top-0 z-10 border-b border-zinc-200 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-black/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-10">
          <Link href="/" className="text-sm text-zinc-500 hover:underline">
            &larr; Repositories
          </Link>
          <button
            onClick={reindex}
            disabled={indexing}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium text-black transition disabled:opacity-50 dark:border-zinc-700 dark:text-white"
          >
            {indexing ? "Indexing..." : "Re-index"}
          </button>
        </div>
      </nav>

      <main className="mx-auto max-w-7xl px-6 py-10 lg:px-10">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          {repository?.name ?? "Repository"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          What the indexer extracted from this repository.
        </p>

        {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

        {indexing && (
          <p className="mt-6 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
            Cloning the repository, parsing every file, and generating embeddings.
            This can take a while on a large repository.
          </p>
        )}

        {graph && (
          <>
            <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-5">
              <StatCard label="Files" value={graph.stats.files} />
              <StatCard label="Symbols" value={graph.stats.symbols} />
              <StatCard label="Functions" value={graph.stats.functions} />
              <StatCard label="Classes" value={graph.stats.classes} />
              <StatCard label="Call edges" value={graph.stats.edges} />
            </div>

            {graph.stats.languages.length > 0 && (
              <div className="mt-8">
                <h2 className="text-sm font-medium text-zinc-500">Languages</h2>
                <div className="mt-3 flex flex-wrap gap-2">
                  {graph.stats.languages.map((entry) => (
                    <span
                      key={entry.language}
                      className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
                    >
                      {entry.language}
                      <span className="ml-2 text-zinc-400">{entry.files}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-10">
              <h2 className="text-lg font-medium text-black dark:text-zinc-50">Call graph</h2>
              <p className="mb-4 mt-1 text-sm text-zinc-500">
                {graph.nodes.length > 0
                  ? `${graph.nodes.length} of ${graph.stats.symbols} symbols take part in a call relationship. The rest are defined but never called within this repository.`
                  : "No call relationships were found."}
              </p>
              <DependencyGraph nodes={graph.nodes} edges={graph.edges} />
            </div>
          </>
        )}

        {graph && graph.stats.files === 0 && (
          <p className="mt-8 rounded-xl border border-dashed border-zinc-300 px-6 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
            This repository has not been indexed yet. Use Re-index above to start.
          </p>
        )}
      </main>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-2xl font-semibold text-black dark:text-zinc-50">{value}</p>
      <p className="mt-1 text-xs uppercase tracking-wide text-zinc-400">{label}</p>
    </div>
  );
}
