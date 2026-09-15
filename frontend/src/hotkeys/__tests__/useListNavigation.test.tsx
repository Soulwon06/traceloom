import type { PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EventSummary } from "../../api/events";
import { groupingModeAtom } from "../../atoms/grouping";
import { collapsedHierarchyNodeIdsAtom } from "../../atoms/hierarchy";
import { buildHierarchyProjection } from "../../hierarchy/grouping";
import { useListNavigation } from "../useListNavigation";

function event(id: string): EventSummary {
  return {
    id,
    seq: 0,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: "http",
    summary: id,
    app: "",
    session: "",
    hierarchy: null,
  };
}

function operation(id: string, spanId: string, parentSpanId: string | null = null): EventSummary {
  return {
    ...event(id),
    hierarchy: {
      runtime: {
        trace_id: "1".repeat(32),
        span_id: spanId.repeat(16),
        parent_span_id: parentSpanId ? parentSpanId.repeat(16) : null,
        role: "operation",
        origin: "traceloom",
      },
      group_memberships: [],
    },
  };
}

function hostEvent(id: string, hostname: string): EventSummary {
  return {
    ...event(id),
    hierarchy: {
      group_memberships: [
        {
          kind: "http_request",
          hostname: { id: hostname, label: hostname },
        },
      ],
    },
  };
}

let mockRequests: EventSummary[] = [];

vi.mock("../../hooks/useFilteredRequests", () => ({
  useFilteredRequests: () => ({ data: mockRequests }),
}));

let currentHash = "";
vi.mock("../../hooks/useSelectedRequestId", () => ({
  useSelectedRequestId: () => [
    currentHash || null,
    (id: string | null) => {
      currentHash = id ?? "";
    },
  ],
}));

const hotkeyCallbacks: Record<string, () => void> = {};
vi.mock("react-hotkeys-hook", () => ({
  useHotkeys: (keys: string, callback: () => void) => {
    for (const key of keys.split(",").map((value) => value.trim())) {
      hotkeyCallbacks[key] = callback;
    }
  },
}));

function renderNavigationHook(store = createStore()) {
  const wrapper = ({ children }: PropsWithChildren) => (
    <Provider store={store}>{children}</Provider>
  );
  renderHook(() => useListNavigation(), { wrapper });
  return store;
}

beforeEach(() => {
  currentHash = "";
  mockRequests = [event("a"), event("b"), event("c")];
  Object.keys(hotkeyCallbacks).forEach((key) => delete hotkeyCallbacks[key]);
});

describe("useListNavigation", () => {
  it("selects the first or last visible item when nothing is selected", () => {
    renderNavigationHook();

    act(() => hotkeyCallbacks.j!());
    expect(currentHash).toBe("a");

    currentHash = "";
    act(() => hotkeyCallbacks.k!());
    expect(currentHash).toBe("c");
  });

  it("moves through the visible hierarchy order instead of API order", () => {
    mockRequests = [operation("child", "b", "a"), operation("parent", "a"), event("sibling")];
    currentHash = "parent";
    const store = renderNavigationHook();

    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("child");

    renderNavigationHook(store);
    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("sibling");
  });

  it("skips descendants of collapsed nodes", () => {
    mockRequests = [operation("child", "b", "a"), operation("parent", "a"), event("sibling")];
    currentHash = "parent";
    const store = createStore();
    store.set(
      collapsedHierarchyNodeIdsAtom,
      new Set([`runtime:${"1".repeat(32)}:${"a".repeat(16)}:parent`]),
    );
    renderNavigationHook(store);

    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("sibling");
  });

  it("moves relative to a selected event hidden by a collapsed operation", () => {
    mockRequests = [operation("child", "b", "a"), operation("parent", "a"), event("sibling")];
    currentHash = "child";
    const store = createStore();
    store.set(
      collapsedHierarchyNodeIdsAtom,
      new Set([`runtime:${"1".repeat(32)}:${"a".repeat(16)}:parent`]),
    );
    renderNavigationHook(store);

    act(() => hotkeyCallbacks.ArrowUp!());
    expect(currentHash).toBe("parent");

    currentHash = "child";
    renderNavigationHook(store);
    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("sibling");
  });

  it("skips events inside collapsed virtual groups", () => {
    mockRequests = [
      hostEvent("api-one", "api.example.com"),
      hostEvent("api-two", "api.example.com"),
      hostEvent("other", "other.example.com"),
    ];
    const apiGroup = buildHierarchyProjection(mockRequests, "http_request:hostname").nodes[0]!;
    expect(apiGroup.kind).toBe("group");

    const store = createStore();
    store.set(groupingModeAtom, "http_request:hostname");
    store.set(collapsedHierarchyNodeIdsAtom, new Set([apiGroup.id]));
    renderNavigationHook(store);

    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("other");
  });

  it("moves relative to a selected event hidden by a collapsed virtual group", () => {
    mockRequests = [
      hostEvent("before", "before.example.com"),
      hostEvent("api-one", "api.example.com"),
      hostEvent("api-two", "api.example.com"),
      hostEvent("after", "after.example.com"),
    ];
    const apiGroup = buildHierarchyProjection(mockRequests, "http_request:hostname").nodes[1]!;
    expect(apiGroup.kind).toBe("group");
    currentHash = "api-one";

    const store = createStore();
    store.set(groupingModeAtom, "http_request:hostname");
    store.set(collapsedHierarchyNodeIdsAtom, new Set([apiGroup.id]));
    renderNavigationHook(store);

    act(() => hotkeyCallbacks.ArrowUp!());
    expect(currentHash).toBe("before");

    currentHash = "api-two";
    renderNavigationHook(store);
    act(() => hotkeyCallbacks.ArrowDown!());
    expect(currentHash).toBe("after");
  });

  it("clamps at the visible list boundaries", () => {
    currentHash = "c";
    const store = renderNavigationHook();
    act(() => hotkeyCallbacks.j!());
    expect(currentHash).toBe("c");

    currentHash = "a";
    renderNavigationHook(store);
    act(() => hotkeyCallbacks.k!());
    expect(currentHash).toBe("a");
  });

  it("ArrowRight expands a collapsed operation before entering its first child", () => {
    mockRequests = [operation("child", "b", "a"), operation("parent", "a")];
    currentHash = "parent";
    const nodeId = `runtime:${"1".repeat(32)}:${"a".repeat(16)}:parent`;
    const store = createStore();
    store.set(collapsedHierarchyNodeIdsAtom, new Set([nodeId]));
    const { rerender } = renderHook(() => useListNavigation(), {
      wrapper: ({ children }: PropsWithChildren) => <Provider store={store}>{children}</Provider>,
    });

    act(() => hotkeyCallbacks.ArrowRight!());
    expect(store.get(collapsedHierarchyNodeIdsAtom).has(nodeId)).toBe(false);
    expect(currentHash).toBe("parent");

    rerender();
    act(() => hotkeyCallbacks.ArrowRight!());
    expect(currentHash).toBe("child");
  });

  it("ArrowLeft collapses an expanded operation before moving to its parent", () => {
    mockRequests = [
      operation("grandchild", "c", "b"),
      operation("child", "b", "a"),
      operation("parent", "a"),
    ];
    currentHash = "child";
    const childNodeId = `runtime:${"1".repeat(32)}:${"b".repeat(16)}:child`;
    const store = renderNavigationHook();

    act(() => hotkeyCallbacks.ArrowLeft!());
    expect(store.get(collapsedHierarchyNodeIdsAtom).has(childNodeId)).toBe(true);
    expect(currentHash).toBe("child");

    renderNavigationHook(store);
    act(() => hotkeyCallbacks.ArrowLeft!());
    expect(currentHash).toBe("parent");
  });

  it("registers all arrow-key shortcuts", () => {
    renderNavigationHook();
    expect(hotkeyCallbacks.ArrowDown).toBeDefined();
    expect(hotkeyCallbacks.ArrowUp).toBeDefined();
    expect(hotkeyCallbacks.ArrowRight).toBeDefined();
    expect(hotkeyCallbacks.ArrowLeft).toBeDefined();
  });
});
