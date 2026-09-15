import { describe, expect, it } from "vitest";
import type { EventSummary } from "../api/events";
import { buildRuntimeTree } from "./runtimeTree";

function event(
  id: string,
  runtime?: {
    trace_id: string;
    span_id: string;
    parent_span_id?: string | null;
    role: "operation" | "annotation";
  },
): EventSummary {
  return {
    id,
    seq: 0,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: runtime?.role === "annotation" ? "log" : "http",
    summary: id,
    app: "",
    session: "",
    hierarchy: runtime
      ? {
          runtime: { ...runtime, origin: "traceloom" },
          group_memberships: [],
        }
      : null,
  };
}

describe("buildRuntimeTree", () => {
  it("links out-of-order children and attaches annotations", () => {
    const child = event("child", {
      trace_id: "1".repeat(32),
      span_id: "b".repeat(16),
      parent_span_id: "a".repeat(16),
      role: "operation",
    });
    const annotation = event("log", {
      trace_id: "1".repeat(32),
      span_id: "a".repeat(16),
      role: "annotation",
    });
    const parent = event("parent", {
      trace_id: "1".repeat(32),
      span_id: "a".repeat(16),
      role: "operation",
    });

    const result = buildRuntimeTree([child, annotation, parent]);

    expect(result.roots).toHaveLength(1);
    expect(result.roots[0]!.event.id).toBe("parent");
    expect(result.roots[0]!.children[0]!.event.id).toBe("child");
    expect(result.roots[0]!.annotations[0]!.id).toBe("log");
  });

  it("keeps missing-parent operations as incomplete roots", () => {
    const orphan = event("orphan", {
      trace_id: "1".repeat(32),
      span_id: "b".repeat(16),
      parent_span_id: "f".repeat(16),
      role: "operation",
    });

    const result = buildRuntimeTree([orphan]);

    expect(result.roots[0]).toMatchObject({ incomplete: true });
  });

  it("preserves conflicting identities without choosing a parent", () => {
    const runtime = {
      trace_id: "1".repeat(32),
      span_id: "a".repeat(16),
      role: "operation" as const,
    };
    const child = event("child", {
      trace_id: runtime.trace_id,
      span_id: "b".repeat(16),
      parent_span_id: runtime.span_id,
      role: "operation",
    });

    const result = buildRuntimeTree([event("first", runtime), event("second", runtime), child]);

    expect(result.roots.map((node) => node.event.id)).toEqual(["first", "second", "child"]);
    expect(result.roots.slice(0, 2).every((node) => node.ambiguous)).toBe(true);
    expect(result.roots[2]!.incomplete).toBe(true);
  });

  it("keeps legacy and detached annotation rows visible", () => {
    const detached = event("detached", {
      trace_id: "1".repeat(32),
      span_id: "a".repeat(16),
      role: "annotation",
    });
    const legacy = event("legacy");

    expect(buildRuntimeTree([detached, legacy]).uncorrelated.map((item) => item.id)).toEqual([
      "legacy",
      "detached",
    ]);
  });
});
