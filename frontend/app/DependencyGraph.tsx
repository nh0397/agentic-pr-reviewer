"use client";

import { useMemo, useState } from "react";

import { HEIGHT, WIDTH, layout } from "./graphLayout";
import type { GraphEdge, GraphNode } from "./graphLayout";

export type { GraphEdge, GraphNode };

export function DependencyGraph({
  nodes,
  edges,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}) {
  const positioned = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const [hovered, setHovered] = useState<number | null>(null);

  const byId = useMemo(
    () => new Map(positioned.map((n) => [n.id, n])),
    [positioned]
  );

  // Which nodes are one hop from the hovered node, used to dim everything else.
  const related = useMemo(() => {
    if (hovered === null) return null;
    const set = new Set<number>([hovered]);
    for (const edge of edges) {
      if (edge.source === hovered) set.add(edge.target);
      if (edge.target === hovered) set.add(edge.source);
    }
    return set;
  }, [hovered, edges]);

  if (positioned.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-zinc-700">
        No call relationships found between symbols in this repository.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full min-w-[700px]"
        role="img"
        aria-label="Call graph of indexed symbols"
      >
        <defs>
          <marker
            id="graph-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" className="fill-zinc-500 dark:fill-zinc-400" />
          </marker>
        </defs>

        {edges.map((edge, i) => {
          const from = byId.get(edge.source);
          const to = byId.get(edge.target);
          if (!from || !to) return null;

          // Stop the line short of the target so the arrowhead sits outside
          // the circle instead of underneath it.
          const angle = Math.atan2(to.y - from.y, to.x - from.x);
          const endX = to.x - Math.cos(angle) * 14;
          const endY = to.y - Math.sin(angle) * 14;

          const dimmed =
            related !== null && !(related.has(edge.source) && related.has(edge.target));

          return (
            <line
              key={i}
              x1={from.x}
              y1={from.y}
              x2={endX}
              y2={endY}
              markerEnd="url(#graph-arrow)"
              className="stroke-zinc-500 dark:stroke-zinc-400"
              strokeWidth={1.5}
              opacity={dimmed ? 0.25 : 1}
            />
          );
        })}

        {positioned.map((node) => {
          const isClass = node.symbol_type === "class";
          const dimmed = related !== null && !related.has(node.id);
          return (
            <g
              key={node.id}
              opacity={dimmed ? 0.3 : 1}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              className="cursor-pointer"
            >
              {/* Shape carries the same distinction as colour, so the graph
                  is still readable in greyscale or with colour blindness.
                  Classes are squares, functions are circles. */}
              {isClass ? (
                <rect
                  x={node.x - (hovered === node.id ? 10 : 7.5)}
                  y={node.y - (hovered === node.id ? 10 : 7.5)}
                  width={hovered === node.id ? 20 : 15}
                  height={hovered === node.id ? 20 : 15}
                  rx={2}
                  className="fill-orange-600 dark:fill-orange-400"
                />
              ) : (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={hovered === node.id ? 11 : 8}
                  className="fill-blue-600 dark:fill-blue-400"
                />
              )}
              <text
                x={node.x}
                y={node.y - 16}
                textAnchor="middle"
                className="fill-zinc-900 text-[11px] font-medium dark:fill-zinc-100"
              >
                {node.name}
              </text>
              {hovered === node.id && (
                <text
                  x={node.x}
                  y={node.y + 26}
                  textAnchor="middle"
                  className="fill-zinc-600 text-[10px] dark:fill-zinc-300"
                >
                  {node.path}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-zinc-200 px-4 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-600 dark:bg-blue-400" />
          Function
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[2px] bg-orange-600 dark:bg-orange-400" />
          Class
        </span>
        <span>Arrow points from caller to callee. Hover a node to isolate it.</span>
      </div>
    </div>
  );
}
