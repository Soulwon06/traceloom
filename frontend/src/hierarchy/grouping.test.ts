import { describe, expect, it } from "vitest";
import type { EventSummary } from "../api/events";
import { availableGroupingOptions } from "./definitions";
import { buildHierarchyProjection, type HierarchyNode } from "./grouping";

type Runtime = NonNullable<NonNullable<EventSummary["hierarchy"]>["runtime"]>;
type Memberships = NonNullable<EventSummary["hierarchy"]>["group_memberships"];

const traceId = "1".repeat(32);

function event(
  id: string,
  { runtime, memberships = [] }: { runtime?: Runtime; memberships?: Memberships } = {},
): EventSummary {
  return {
    id,
    seq: 0,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: "http",
    summary: id,
    app: "",
    session: "",
    hierarchy: runtime || memberships.length ? { runtime, group_memberships: memberships } : null,
  };
}

function operation(spanId: string, parentSpanId?: string): Runtime {
  return {
    trace_id: traceId,
    span_id: spanId.repeat(16),
    parent_span_id: parentSpanId?.repeat(16),
    role: "operation",
    origin: "traceloom",
  };
}

const pytestMembership = {
  kind: "pytest" as const,
  test_directory: { id: "tests", label: "tests" },
  test_file: { id: "tests/test_api.py", label: "test_api.py" },
  test_class: { id: "tests/test_api.py::TestApi", label: "TestApi" },
  test_case: { id: "tests/test_api.py::TestApi::test_get", label: "test_get" },
};

function hostMembership(id: string, label = id) {
  return { kind: "http_request" as const, hostname: { id, label } };
}

function child(node: HierarchyNode, index = 0): HierarchyNode {
  expect(node.kind === "group" || node.kind === "operation").toBe(true);
  if (node.kind === "event") throw new Error("event nodes have no children");
  return node.children[index]!;
}

describe("composed hierarchy projection", () => {
  it("always preserves runtime parenthood when virtual grouping is disabled", () => {
    const parent = event("test", { runtime: operation("a") });
    const request = event("request", { runtime: operation("b", "a") });

    const result = buildHierarchyProjection([request, parent], "none");

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0]).toMatchObject({ kind: "operation", event: { id: "test" } });
    expect(child(result.nodes[0]!)).toMatchObject({
      kind: "operation",
      event: { id: "request" },
    });
  });

  it("places inherited pytest groups above a runtime tree", () => {
    const parent = event("test", {
      runtime: operation("a"),
      memberships: [pytestMembership],
    });
    const request = event("request", {
      runtime: operation("b", "a"),
      memberships: [pytestMembership, hostMembership("api.example.com")],
    });

    const result = buildHierarchyProjection([request, parent], "pytest:test_file");

    expect(result.nodes[0]).toMatchObject({ kind: "group", label: "tests" });
    const file = child(result.nodes[0]!);
    expect(file).toMatchObject({ kind: "group", label: "test_api.py" });
    const test = child(file);
    expect(test).toMatchObject({ kind: "operation", event: { id: "test" } });
    expect(child(test)).toMatchObject({ kind: "operation", event: { id: "request" } });
  });

  it("inserts a hostname group where membership starts inside a runtime tree", () => {
    const parent = event("test", {
      runtime: operation("a"),
      memberships: [pytestMembership],
    });
    const request = event("request", {
      runtime: operation("b", "a"),
      memberships: [pytestMembership, hostMembership("api.example.com")],
    });

    const result = buildHierarchyProjection([request, parent], "http_request:hostname");

    const test = result.nodes[0]!;
    expect(test).toMatchObject({ kind: "operation", event: { id: "test" } });
    const host = child(test);
    expect(host).toMatchObject({ kind: "group", label: "api.example.com" });
    expect(child(host)).toMatchObject({ kind: "operation", event: { id: "request" } });
  });

  it("merges only adjacent equal groups and preserves sibling order", () => {
    const events = [
      event("example-1", {
        runtime: operation("a"),
        memberships: [hostMembership("example.com")],
      }),
      event("foo-1", {
        runtime: operation("b"),
        memberships: [hostMembership("foo.com")],
      }),
      event("foo-2", {
        runtime: operation("c"),
        memberships: [hostMembership("foo.com")],
      }),
      event("example-2", {
        runtime: operation("d"),
        memberships: [hostMembership("example.com")],
      }),
      event("example-3", {
        runtime: operation("e"),
        memberships: [hostMembership("example.com")],
      }),
    ];

    const result = buildHierarchyProjection(events, "http_request:hostname");

    expect(result.nodes.map((node) => (node.kind === "group" ? node.label : node.kind))).toEqual([
      "example.com",
      "foo.com",
      "example.com",
    ]);
    expect(result.nodes.map((node) => (node.kind === "group" ? node.children.length : 0))).toEqual([
      1, 2, 2,
    ]);
    expect(result.nodes[0]!.id).not.toBe(result.nodes[2]!.id);
  });

  it("includes preceding pytest levels and skips missing optional levels", () => {
    const membership = { ...pytestMembership, test_directory: null, test_class: null };
    const result = buildHierarchyProjection(
      [event("one", { memberships: [membership] })],
      "pytest:test_case",
    );

    expect(result.nodes[0]).toMatchObject({ kind: "group", label: "test_api.py" });
    expect(child(result.nodes[0]!)).toMatchObject({ kind: "group", label: "test_get" });
  });

  it("uses IDs rather than labels for adjacent virtual group identity", () => {
    const result = buildHierarchyProjection(
      [
        event("one", { memberships: [hostMembership("one", "API")] }),
        event("two", { memberships: [hostMembership("two", "API")] }),
      ],
      "http_request:hostname",
    );

    expect(result.nodes).toHaveLength(2);
    expect(result.nodes[0]!.id).not.toBe(result.nodes[1]!.id);
  });

  it("keeps a virtual group id when polling prepends another member", () => {
    const originalEvents = [
      event("existing-newer", { memberships: [hostMembership("api.example.com")] }),
      event("existing-older", { memberships: [hostMembership("api.example.com")] }),
    ];
    const original = buildHierarchyProjection(originalEvents, "http_request:hostname");

    const updated = buildHierarchyProjection(
      [event("new-head", { memberships: [hostMembership("api.example.com")] }), ...originalEvents],
      "http_request:hostname",
    );

    expect(updated.nodes[0]!.id).toBe(original.nodes[0]!.id);
  });

  it("offers only virtual granularities represented in loaded records", () => {
    const membership = { ...pytestMembership, test_directory: null, test_class: null };
    const values = availableGroupingOptions([
      event("one", { memberships: [membership, hostMembership("api")] }),
    ]).map((option) => option.value);

    expect(values).toEqual([
      "none",
      "pytest:test_file",
      "pytest:test_case",
      "http_request:hostname",
    ]);
  });
});
