import { createStore, Provider } from "jotai";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventSummary } from "../api/events";
import { groupingModeAtom } from "../atoms/grouping";
import RequestList from "./RequestList";

const setSelectedId = vi.fn();
let events: EventSummary[] = [];

vi.mock("../hooks/useFilteredRequests", () => ({
  useFilteredRequests: () => ({ data: events }),
}));
vi.mock("../hooks/useSelectedRequestId", () => ({
  useSelectedRequestId: () => [null, setSelectedId],
}));
vi.mock("./RequestListItem", () => ({
  default: ({ item, onClick }: { item: EventSummary; onClick: () => void }) => (
    <button onClick={onClick}>{item.id}</button>
  ),
}));

function hostEvent(id: string): EventSummary {
  return {
    id,
    seq: 0,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: "http",
    summary: id,
    app: "",
    session: "",
    hierarchy: {
      group_memberships: [
        {
          kind: "http_request",
          hostname: { id: "api.example.com", label: "api.example.com" },
        },
      ],
    },
  };
}

describe("RequestList hierarchy rendering", () => {
  afterEach(cleanup);

  beforeEach(() => {
    events = [hostEvent("event-uuid")];
    setSelectedId.mockReset();
  });

  it("renders stable virtual groups without replacing event selection IDs", () => {
    const store = createStore();
    store.set(groupingModeAtom, "http_request:hostname");
    const { container } = render(
      <Provider store={store}>
        <RequestList />
      </Provider>,
    );

    expect(screen.getByText("api.example.com")).toBeInTheDocument();
    expect(screen.getByText("1 loaded record")).toBeInTheDocument();
    expect(
      container.querySelector(
        '[data-group-id^="group:http_request:hostname:root:api.example.com:"]',
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "event-uuid" }));
    expect(setSelectedId).toHaveBeenCalledWith("event-uuid");
  });

  it("collapses and expands virtual group children", () => {
    const store = createStore();
    store.set(groupingModeAtom, "http_request:hostname");
    render(
      <Provider store={store}>
        <RequestList />
      </Provider>,
    );

    fireEvent.click(screen.getByText("api.example.com"));
    expect(screen.queryByRole("button", { name: "event-uuid" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("api.example.com"));
    expect(screen.getByRole("button", { name: "event-uuid" })).toBeInTheDocument();
  });

  it("renders runtime parenthood when no virtual grouping is selected", () => {
    const traceId = "1".repeat(32);
    events = [
      {
        ...hostEvent("child"),
        hierarchy: {
          runtime: {
            trace_id: traceId,
            span_id: "b".repeat(16),
            parent_span_id: "a".repeat(16),
            role: "operation",
            origin: "traceloom",
          },
          group_memberships: [],
        },
      },
      {
        ...hostEvent("parent"),
        hierarchy: {
          runtime: {
            trace_id: traceId,
            span_id: "a".repeat(16),
            parent_span_id: null,
            role: "operation",
            origin: "traceloom",
          },
          group_memberships: [],
        },
      },
      {
        ...hostEvent("leaf"),
        hierarchy: {
          runtime: {
            trace_id: traceId,
            span_id: "c".repeat(16),
            parent_span_id: null,
            role: "operation",
            origin: "traceloom",
          },
          group_memberships: [],
        },
      },
    ];
    const store = createStore();

    render(
      <Provider store={store}>
        <RequestList />
      </Provider>,
    );

    const parentRow = screen.getByRole("button", { name: "parent" }).parentElement!;
    const leafRow = screen.getByRole("button", { name: "leaf" }).parentElement!;
    expect(getComputedStyle(parentRow).paddingLeft).toBe(getComputedStyle(leafRow).paddingLeft);

    fireEvent.click(screen.getByLabelText("Collapse operation"));
    expect(screen.queryByRole("button", { name: "child" })).not.toBeInTheDocument();
  });

  it("keeps a full indentation step between virtual groups and runtime operations", () => {
    const traceId = "1".repeat(32);
    const membership = {
      kind: "pytest" as const,
      test_directory: { id: "tests", label: "tests" },
      test_file: { id: "tests/test_api.py", label: "test_api.py" },
      test_class: null,
      test_case: { id: "tests/test_api.py::test_get", label: "test_get" },
    };
    events = [
      {
        ...hostEvent("child"),
        hierarchy: {
          runtime: {
            trace_id: traceId,
            span_id: "b".repeat(16),
            parent_span_id: "a".repeat(16),
            role: "operation",
            origin: "traceloom",
          },
          group_memberships: [membership],
        },
      },
      {
        ...hostEvent("parent"),
        hierarchy: {
          runtime: {
            trace_id: traceId,
            span_id: "a".repeat(16),
            parent_span_id: null,
            role: "operation",
            origin: "traceloom",
          },
          group_memberships: [membership],
        },
      },
    ];
    const store = createStore();
    store.set(groupingModeAtom, "pytest:test_file");

    render(
      <Provider store={store}>
        <RequestList />
      </Provider>,
    );

    const directoryRow = screen.getByText("tests").closest(".MuiListItemButton-root")!;
    const fileRow = screen.getByText("test_api.py").closest(".MuiListItemButton-root")!;
    const operationToggle = screen.getAllByLabelText("Collapse operation")[0]!;
    const directoryOffset = Number.parseFloat(getComputedStyle(directoryRow).paddingLeft);
    const fileOffset = Number.parseFloat(getComputedStyle(fileRow).paddingLeft);
    const operationOffset = Number.parseFloat(getComputedStyle(operationToggle).left);

    expect(fileOffset - directoryOffset).toBe(12);
    expect(operationOffset - fileOffset).toBe(12);
  });
});
