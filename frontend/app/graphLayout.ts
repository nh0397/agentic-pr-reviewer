export type GraphNode = {
  id: number;
  name: string;
  symbol_type: string;
  path: string;
};

export type GraphEdge = {
  source: number;
  target: number;
};

export type Positioned = GraphNode & { x: number; y: number };

export const WIDTH = 900;
export const HEIGHT = 560;

/**
 * Fruchterman-Reingold force layout, run to completion once rather than
 * animated. Nodes repel each other, edges pull their endpoints together,
 * and a cooling factor shrinks the step size so it settles instead of
 * oscillating. Small graphs settle in a few hundred iterations, which is
 * fast enough to do synchronously while rendering.
 *
 * Kept free of React and JSX so the layout can be exercised on its own.
 */
export function layout(nodes: GraphNode[], edges: GraphEdge[]): Positioned[] {
  const count = nodes.length;
  if (count === 0) return [];

  const area = WIDTH * HEIGHT;
  const k = Math.sqrt(area / count) * 0.6;

  // Seed on a circle: deterministic (same graph always renders the same
  // way) and already spread out, so the simulation has less work to do.
  const placed: Positioned[] = nodes.map((node, i) => {
    const angle = (i / count) * Math.PI * 2;
    return {
      ...node,
      x: WIDTH / 2 + Math.cos(angle) * (WIDTH / 4),
      y: HEIGHT / 2 + Math.sin(angle) * (HEIGHT / 4),
    };
  });

  const indexById = new Map(placed.map((n, i) => [n.id, i]));

  // Repulsion compares every pair, so cost grows with the square of the
  // node count. Small graphs get the full run; larger ones get fewer
  // iterations so this stays well under a frame budget instead of freezing
  // the page. Big graphs settle into their overall shape early anyway, so
  // the extra passes mostly refine detail that is not visible at that size.
  const iterations = count <= 60 ? 300 : Math.max(100, Math.round(18000 / count));

  const initialTemperature = WIDTH / 8;
  const finalTemperature = 0.05;
  // Derive the per-step cooling from the iteration count so the layout
  // always finishes cold. A fixed rate tuned for 300 steps would leave a
  // shorter run still hot, i.e. nodes still visibly drifting when it stops.
  const cooling = Math.pow(finalTemperature / initialTemperature, 1 / iterations);
  let temperature = initialTemperature;

  for (let step = 0; step < iterations; step++) {
    const dx = new Array(count).fill(0);
    const dy = new Array(count).fill(0);

    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        let diffX = placed[i].x - placed[j].x;
        let diffY = placed[i].y - placed[j].y;
        let distance = Math.hypot(diffX, diffY);
        if (distance < 0.01) {
          // Perfectly coincident nodes have no direction to separate along,
          // so nudge them apart deterministically.
          diffX = (i % 2 === 0 ? 1 : -1) * 0.1;
          diffY = 0.1;
          distance = Math.hypot(diffX, diffY);
        }
        const repulsion = (k * k) / distance;
        const ux = (diffX / distance) * repulsion;
        const uy = (diffY / distance) * repulsion;
        dx[i] += ux;
        dy[i] += uy;
        dx[j] -= ux;
        dy[j] -= uy;
      }
    }

    for (const edge of edges) {
      const a = indexById.get(edge.source);
      const b = indexById.get(edge.target);
      if (a === undefined || b === undefined || a === b) continue;
      const diffX = placed[a].x - placed[b].x;
      const diffY = placed[a].y - placed[b].y;
      const distance = Math.max(Math.hypot(diffX, diffY), 0.01);
      const attraction = (distance * distance) / k;
      const ux = (diffX / distance) * attraction;
      const uy = (diffY / distance) * attraction;
      dx[a] -= ux;
      dy[a] -= uy;
      dx[b] += ux;
      dy[b] += uy;
    }

    for (let i = 0; i < count; i++) {
      const displacement = Math.max(Math.hypot(dx[i], dy[i]), 0.01);
      const limited = Math.min(displacement, temperature);
      placed[i].x += (dx[i] / displacement) * limited;
      placed[i].y += (dy[i] / displacement) * limited;
      // Keep everything inside the viewport with a margin for labels.
      placed[i].x = Math.min(WIDTH - 60, Math.max(60, placed[i].x));
      placed[i].y = Math.min(HEIGHT - 30, Math.max(30, placed[i].y));
    }

    temperature *= cooling;
  }

  return placed;
}
