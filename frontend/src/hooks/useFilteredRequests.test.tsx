import type { PropsWithChildren } from "react";
import { createStore, Provider } from "jotai";
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EventSummary } from "../api/events";
import {
  eventTypeFilterAtom,
  hostFilterAtom,
  searchFilterAtom,
  sessionFilterAtom,
} from "../atoms/filters";
import { useFilteredRequests } from "./useFilteredRequests";

const mocks = vi.hoisted(() => ({
  useEventStore: vi.fn(),
  useEventIds: vi.fn(),
  useSearchEvents: vi.fn(),
}));

vi.mock("../api/events", () => ({
  useEventStore: mocks.useEventStore,
  useEventIds: mocks.useEventIds,
  useSearchEvents: mocks.useSearchEvents,
}));

function event(id: string, overrides: Partial<EventSummary> = {}): EventSummary {
  return {
    id,
    seq: 1,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: "http",
    summary: id,
    app: "",
    session: "",
    host: "api.example.com",
    method: "GET",
    status_code: 200,
    hierarchy: null,
    ...overrides,
  };
}

const httpEvent = event("http-1");
const logEvent = event("log-1", { event_type: "log", host: null, method: null });
const otherHostEvent = event("http-2", { host: "api.stripe.com" });
const allEvents = [httpEvent, logEvent, otherHostEvent];

function renderWith(setup: (store: ReturnType<typeof createStore>) => void = () => {}) {
  const store = createStore();
  setup(store);
  const wrapper = ({ children }: PropsWithChildren) => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(() => useFilteredRequests(), { wrapper });
}

describe("useFilteredRequests", () => {
  beforeEach(() => {
    mocks.useEventStore.mockReset();
    mocks.useEventIds.mockReset();
    mocks.useSearchEvents.mockReset();
    mocks.useEventStore.mockReturnValue({
      data: { epoch: "e:0", maxSeq: 3, events: allEvents },
      isLoading: false,
    });
    mocks.useEventIds.mockReturnValue({ data: undefined });
    mocks.useSearchEvents.mockReturnValue({ data: undefined });
  });

  it("returns the store unchanged when no filter is active", () => {
    const { result } = renderWith();

    // Identity matters: a new array would rebuild the hierarchy projection.
    expect(result.current.data).toBe(allEvents);
  });

  it("keys the store by the session filter so the fetch stays bounded", () => {
    renderWith((store) => store.set(sessionFilterAtom, "debug-payment"));

    expect(mocks.useEventStore).toHaveBeenCalledWith("debug-payment");
  });

  it("applies structural filters locally without refetching", () => {
    const { result } = renderWith((store) => store.set(eventTypeFilterAtom, "log"));

    expect(result.current.data).toEqual([logEvent]);
    expect(mocks.useEventStore).toHaveBeenCalledWith(undefined);
  });

  it("filters by host from the summary", () => {
    const { result } = renderWith((store) => store.set(hostFilterAtom, "api.stripe.com"));

    expect(result.current.data).toEqual([otherHostEvent]);
  });

  it("intersects with server-side search, which alone can match bodies", () => {
    mocks.useEventIds.mockReturnValue({ data: { epoch: "e:0", ids: ["http-2"] } });

    const { result } = renderWith((store) => store.set(searchFilterAtom, "sentinel"));

    expect(mocks.useEventIds).toHaveBeenCalledWith(
      { search: "sentinel" },
      { enabled: true, refetchInterval: 3_000 },
    );
    expect(result.current.data).toEqual([otherHostEvent]);
  });

  it("fetches matches directly when they are older than the loaded store", () => {
    // The store was truncated by the page limit, so this match is not in it.
    const oldEvent = event("http-old");
    mocks.useEventIds.mockReturnValue({ data: { epoch: "e:0", ids: ["http-old"] } });
    mocks.useSearchEvents.mockReturnValue({
      data: { epoch: "e:0", max_seq: 3, events: [oldEvent] },
    });

    const { result } = renderWith((store) => store.set(searchFilterAtom, "sentinel"));

    expect(mocks.useSearchEvents).toHaveBeenCalledWith(
      { search: "sentinel" },
      { enabled: true, refetchInterval: 3_000 },
    );
    expect(result.current.data).toEqual([oldEvent]);
  });

  it("does not fetch matches directly when the store holds them all", () => {
    mocks.useEventIds.mockReturnValue({ data: { epoch: "e:0", ids: ["http-2"] } });

    renderWith((store) => store.set(searchFilterAtom, "sentinel"));

    expect(mocks.useSearchEvents).toHaveBeenCalledWith(
      { search: "sentinel" },
      { enabled: false, refetchInterval: 3_000 },
    );
  });

  it("does not run the search query when the box is empty", () => {
    renderWith();

    expect(mocks.useEventIds).toHaveBeenCalledWith(
      { search: "" },
      { enabled: false, refetchInterval: 3_000 },
    );
  });
});
