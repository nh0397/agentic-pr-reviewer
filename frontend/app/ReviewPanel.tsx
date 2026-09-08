"use client";

import { useState } from "react";

export type Finding = {
  id: number;
  severity: string;
  title: string;
  body: string;
  file_path: string | null;
  line: number | null;
  evidence: string | null;
};

export type ToolCall = {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
};

export type Review = {
  id: number;
  pr_number: number;
  pr_title: string | null;
  status: string;
  summary: string | null;
  error: string | null;
  steps_used: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  created_at: string;
  finished_at: string | null;
  tool_calls: ToolCall[];
  findings: Finding[];
};

// Ordered worst-first so the list can be sorted by seriousness.
const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  low: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  info: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

function severityStyle(severity: string): string {
  return SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info;
}

export function ReviewPanel({ review }: { review: Review }) {
  const [showTrail, setShowTrail] = useState(false);

  const findings = [...review.findings].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
  );

  return (
    <div className="mt-6">
      {review.summary && (
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="text-sm font-medium uppercase tracking-wide text-zinc-500">Summary</h3>
          <p className="mt-2 text-black dark:text-zinc-100">{review.summary}</p>
        </div>
      )}

      {review.error && (
        <p className="mt-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {review.error}
        </p>
      )}

      <div className="mt-6">
        <h3 className="text-lg font-medium text-black dark:text-zinc-50">
          {findings.length === 0
            ? "No findings"
            : `${findings.length} finding${findings.length === 1 ? "" : "s"}`}
        </h3>
        {findings.length === 0 && review.status === "succeeded" && (
          <p className="mt-2 text-sm text-zinc-500">
            The agent investigated and did not find anything worth raising.
          </p>
        )}

        <div className="mt-4 flex flex-col gap-3">
          {findings.map((finding) => (
            <div
              key={finding.id}
              className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${severityStyle(
                    finding.severity
                  )}`}
                >
                  {finding.severity}
                </span>
                <span className="font-medium text-black dark:text-zinc-50">{finding.title}</span>
              </div>

              {finding.file_path && (
                <p className="mt-1 font-mono text-xs text-zinc-500">
                  {finding.file_path}
                  {finding.line ? `:${finding.line}` : ""}
                </p>
              )}

              <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                {finding.body}
              </p>

              {finding.evidence && (
                <p className="mt-3 border-l-2 border-zinc-300 pl-3 text-xs text-zinc-500 dark:border-zinc-700">
                  <span className="font-medium">Evidence: </span>
                  {finding.evidence}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {review.tool_calls.length > 0 && (
        <div className="mt-6">
          <button
            onClick={() => setShowTrail((open) => !open)}
            className="text-sm text-zinc-600 underline-offset-2 hover:underline dark:text-zinc-400"
          >
            {showTrail ? "Hide" : "Show"} how the agent investigated (
            {review.tool_calls.length} tool call
            {review.tool_calls.length === 1 ? "" : "s"}
            {review.steps_used ? `, ${review.steps_used} steps` : ""})
          </button>

          {showTrail && (
            <ol className="mt-3 flex flex-col gap-2">
              {review.tool_calls.map((call, i) => (
                <li
                  key={i}
                  className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950"
                >
                  <p className="font-mono text-xs text-black dark:text-zinc-200">
                    <span className="text-zinc-400">{i + 1}. </span>
                    {call.tool}({formatArgs(call.arguments)})
                  </p>
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-zinc-500">
                    {formatResult(call.result)}
                  </pre>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");
}

function formatResult(result: unknown): string {
  const text = typeof result === "string" ? result : JSON.stringify(result, null, 2);
  // Tool results can be long; the trail is for orientation, not full reading.
  return text.length > 1200 ? `${text.slice(0, 1200)}\n...` : text;
}
