import { describe, expect, it } from "vitest";
import type { EventSummary } from "../api/events";
import type { GroupingMode } from "./definitions";
import { buildHierarchyProjection } from "./grouping";
import { buildHierarchyNavigation } from "./navigation";

const traceId = "1".repeat(32);

function event(
  id: string,
  runtime: {
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
    event_type: runtime.role === "annotation" ? "log" : "http",
    summary: id,
    app: "",
    session: "",
    hierarchy: {
      runtime: { ...runtime, origin: "traceloom" },
      group_memberships: [
        {
          kind: "pytest",
          test_directory: { id: "tests", label: "tests" },
          test_file: { id: "tests/test_example.py", label: "test_example.py" },
          test_class: null,
          test_case: { id: `tests/test_example.py::${id}`, label: id },
        },
      ],
    },
  };
}

describe("buildHierarchyNavigation", () => {
  it.each<GroupingMode>(["none", "pytest:test_file"])(
    "visits runtime children after annotations when grouping by %s",
    (mode) => {
      const parent = event("parent", {
        trace_id: traceId,
        span_id: "a".repeat(16),
        role: "operation",
      });
      const annotation = event("annotation", {
        trace_id: traceId,
        span_id: "a".repeat(16),
        role: "annotation",
      });
      const child = event("child", {
        trace_id: traceId,
        span_id: "b".repeat(16),
        parent_span_id: "a".repeat(16),
        role: "operation",
      });
      const next = event("next", {
        trace_id: "2".repeat(32),
        span_id: "c".repeat(16),
        role: "operation",
      });

      const projection = buildHierarchyProjection([parent, annotation, child, next], mode);
      const navigation = buildHierarchyNavigation(projection, new Set());

      expect(navigation.visibleEventIds).toEqual(["parent", "annotation", "child", "next"]);
      expect(navigation.parentEventIdByEventId.get("child")).toBe("parent");
      expect(navigation.firstChildEventIdByEventId.get("parent")).toBe("annotation");
    },
  );
});
