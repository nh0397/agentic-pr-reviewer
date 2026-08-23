"use client";

export type IndexJob = {
  id: number;
  repository_id: number;
  status: "queued" | "running" | "succeeded" | "failed";
  queue_position: number;
  phase: string | null;
  detail: string | null;
  progress_current: number | null;
  progress_total: number | null;
  error: string | null;
};

// The order indexing actually runs in, used to show which step it is on.
const PHASES = [
  { key: "cloning", label: "Clone" },
  { key: "parsing", label: "Parse" },
  { key: "resolving", label: "Link" },
  { key: "embedding", label: "Embed" },
  { key: "storing", label: "Store" },
] as const;

function queuedText(job: IndexJob): string {
  if (job.queue_position === 0) return "Next in queue";
  const n = job.queue_position;
  return `Waiting behind ${n} ${n === 1 ? "repository" : "repositories"}`;
}

export function IndexProgress({ job }: { job: IndexJob }) {
  if (job.status === "queued") {
    return <p className="mt-2 text-xs text-zinc-500">{queuedText(job)}</p>;
  }

  // "preparing" runs before the first named phase, so nothing is active yet.
  const activeIndex = PHASES.findIndex((p) => p.key === job.phase);
  const hasBar =
    job.progress_total !== null &&
    job.progress_current !== null &&
    job.progress_total > 0;
  const percent = hasBar
    ? Math.round((job.progress_current! / job.progress_total!) * 100)
    : null;

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1">
        {PHASES.map((phase, i) => {
          const done = activeIndex > i;
          const active = activeIndex === i;
          return (
            <div key={phase.key} className="flex flex-1 flex-col items-center gap-1">
              <span
                className={`h-1 w-full rounded-full ${
                  done
                    ? "bg-emerald-500"
                    : active
                      ? "bg-amber-500"
                      : "bg-zinc-200 dark:bg-zinc-700"
                }`}
              />
              <span
                className={`text-[9px] leading-none ${
                  active
                    ? "font-medium text-amber-700 dark:text-amber-400"
                    : done
                      ? "text-emerald-700 dark:text-emerald-500"
                      : "text-zinc-400 dark:text-zinc-600"
                }`}
              >
                {phase.label}
              </span>
            </div>
          );
        })}
      </div>

      <p className="mt-2 truncate text-xs text-zinc-600 dark:text-zinc-400">
        {job.detail ?? "Starting..."}
      </p>

      {percent !== null && (
        <div className="mt-1.5 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
            <div
              className="h-full rounded-full bg-blue-600 transition-[width] duration-500 dark:bg-blue-400"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="shrink-0 text-[10px] tabular-nums text-zinc-500">{percent}%</span>
        </div>
      )}
    </div>
  );
}
