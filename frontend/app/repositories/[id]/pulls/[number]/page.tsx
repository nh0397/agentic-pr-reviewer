"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { API_BASE_URL, fetchOpts, useSession } from "../../../../useSession";
import { ReviewPanel, type Review } from "../../../../ReviewPanel";

type ChangedFile = {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  patch: string | null;
};

type PullRequest = {
  number: number;
  title: string;
  body: string | null;
  state: string;
  author: string;
  html_url: string;
  base_ref: string;
  head_ref: string;
  additions: number;
  deletions: number;
  changed_files: ChangedFile[];
};

// What the agent is doing while the request is open. The call is synchronous
// and takes tens of seconds, so showing nothing would look like a hang.
const WORKING_STEPS = [
  "Cloning the repository for context",
  "Reading the diff",
  "Looking up the symbols it touches",
  "Checking what depends on them",
  "Writing up findings",
];

export default function PullRequestPage({
  params,
}: {
  params: Promise<{ id: string; number: string }>;
}) {
  const { id, number } = use(params);
  const { user, checkingSession, backendUnreachable } = useSession();
  const router = useRouter();

  const [pullRequest, setPullRequest] = useState<PullRequest | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(false);
  const [workingStep, setWorkingStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!checkingSession && !user && !backendUnreachable) router.replace("/login");
  }, [checkingSession, user, backendUnreachable, router]);

  const load = useCallback(async () => {
    try {
      const [prRes, reviewsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/repositories/${id}/pulls/${number}`, fetchOpts),
        fetch(`${API_BASE_URL}/api/repositories/${id}/reviews`, fetchOpts),
      ]);
      if (prRes.ok) setPullRequest(await prRes.json());
      if (reviewsRes.ok) {
        // Most recent review for this PR, if one has been run before.
        const all = await reviewsRes.json();
        const mine = all.find(
          (r: { pr_number: number }) => r.pr_number === Number(number)
        );
        if (mine) {
          const detail = await fetch(
            `${API_BASE_URL}/api/repositories/${id}/reviews/${mine.id}`,
            fetchOpts
          );
          if (detail.ok) setReview(await detail.json());
        }
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, [id, number]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  // Advance the reassurance text while the request is open.
  useEffect(() => {
    if (!reviewing) return;
    setWorkingStep(0);
    const timer = setInterval(
      () => setWorkingStep((s) => Math.min(s + 1, WORKING_STEPS.length - 1)),
      6000
    );
    return () => clearInterval(timer);
  }, [reviewing]);

  async function runReview() {
    setReviewing(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/repositories/${id}/pulls/${number}/review`,
        { ...fetchOpts, method: "POST" }
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `Backend responded with ${res.status}`);
      setReview(body as Review);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setReviewing(false);
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
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link
            href={`/repositories/${id}`}
            className="text-sm text-zinc-500 hover:underline"
          >
            &larr; Repository
          </Link>
          <button
            onClick={runReview}
            disabled={reviewing}
            className="rounded-lg bg-black px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50 dark:bg-white dark:text-black"
          >
            {reviewing ? "Reviewing..." : review ? "Review again" : "Review this PR"}
          </button>
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-10">
        {pullRequest && (
          <>
            <div className="flex flex-wrap items-baseline gap-2">
              <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
                {pullRequest.title}
              </h1>
              <a
                href={pullRequest.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-zinc-500 hover:underline"
              >
                #{pullRequest.number}
              </a>
            </div>
            <p className="mt-1 text-sm text-zinc-500">
              {pullRequest.author} &middot; {pullRequest.head_ref} &rarr;{" "}
              {pullRequest.base_ref} &middot;{" "}
              <span className="text-emerald-600">+{pullRequest.additions}</span>{" "}
              <span className="text-red-600">-{pullRequest.deletions}</span> across{" "}
              {pullRequest.changed_files.length} file
              {pullRequest.changed_files.length === 1 ? "" : "s"}
            </p>
          </>
        )}

        {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

        {reviewing && (
          <div className="mt-6 rounded-xl border border-amber-300 bg-amber-50 px-4 py-4 dark:border-amber-900 dark:bg-amber-950">
            <p className="text-sm font-medium text-amber-900 dark:text-amber-300">
              The agent is investigating. This usually takes 20 to 60 seconds.
            </p>
            <p className="mt-1 text-sm text-amber-800 dark:text-amber-400">
              {WORKING_STEPS[workingStep]}...
            </p>
          </div>
        )}

        {review && !reviewing && <ReviewPanel review={review} />}

        {pullRequest && (
          <div className="mt-10">
            <h2 className="text-lg font-medium text-black dark:text-zinc-50">Changed files</h2>
            <div className="mt-4 flex flex-col gap-3">
              {pullRequest.changed_files.map((file) => (
                <details
                  key={file.path}
                  className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <summary className="cursor-pointer px-4 py-3 text-sm">
                    <span className="font-mono text-black dark:text-zinc-100">{file.path}</span>
                    <span className="ml-2 text-xs text-zinc-500">
                      {file.status} &middot;{" "}
                      <span className="text-emerald-600">+{file.additions}</span>{" "}
                      <span className="text-red-600">-{file.deletions}</span>
                    </span>
                  </summary>
                  <pre className="max-h-96 overflow-auto border-t border-zinc-200 px-4 py-3 text-[11px] leading-relaxed text-zinc-700 dark:border-zinc-800 dark:text-zinc-300">
                    {file.patch ?? "(no patch available)"}
                  </pre>
                </details>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
