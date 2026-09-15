import type { EventSummary } from "../api/events";

export interface RuntimeTreeNode {
  kind: "operation";
  id: string;
  event: EventSummary;
  annotations: EventSummary[];
  children: RuntimeTreeNode[];
  ambiguous: boolean;
  incomplete: boolean;
}

export interface RuntimeTreeProjection {
  roots: RuntimeTreeNode[];
  uncorrelated: EventSummary[];
}

function identity(traceId: string, spanId: string): string {
  return `${traceId}:${spanId}`;
}

export function buildRuntimeTree(events: EventSummary[]): RuntimeTreeProjection {
  const operations = new Map<string, RuntimeTreeNode[]>();
  const annotations = new Map<string, EventSummary[]>();
  const uncorrelated: EventSummary[] = [];

  for (const event of events) {
    const runtime = event.hierarchy?.runtime;
    if (!runtime) {
      uncorrelated.push(event);
      continue;
    }
    const key = identity(runtime.trace_id, runtime.span_id);
    if (runtime.role === "annotation") {
      const existing = annotations.get(key) ?? [];
      existing.push(event);
      annotations.set(key, existing);
      continue;
    }
    const existing = operations.get(key) ?? [];
    existing.push({
      kind: "operation",
      id: `runtime:${key}:${event.id}`,
      event,
      annotations: [],
      children: [],
      ambiguous: false,
      incomplete: false,
    });
    operations.set(key, existing);
  }

  for (const [key, rows] of operations) {
    if (rows.length > 1) rows.forEach((node) => (node.ambiguous = true));
    const attached = annotations.get(key) ?? [];
    if (rows.length === 1) {
      rows[0]!.annotations.push(...attached);
      annotations.delete(key);
    }
  }

  const roots: RuntimeTreeNode[] = [];
  for (const rows of operations.values()) {
    for (const node of rows) {
      const runtime = node.event.hierarchy!.runtime!;
      if (!runtime.parent_span_id || node.ambiguous) {
        roots.push(node);
        continue;
      }
      const parentRows = operations.get(identity(runtime.trace_id, runtime.parent_span_id));
      if (parentRows?.length === 1 && !parentRows[0]!.ambiguous) {
        parentRows[0]!.children.push(node);
      } else {
        node.incomplete = true;
        roots.push(node);
      }
    }
  }

  for (const detached of annotations.values()) uncorrelated.push(...detached);
  return { roots, uncorrelated };
}
