import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useEventStore, type EventSummary } from "./events";

function event(seq: number): EventSummary {
  return {
    id: `event-${seq}`,
    seq,
    timestamp: "2026-01-01T00:00:00Z",
    event_type: "http",
    summary: `event ${seq}`,
    app: "",
    session: "",
    hierarchy: null,
  };
}

/** Newest first, the order the API returns. */
function page(epoch: string, maxSeq: number, seqs: number[]) {
  return {
    epoch,
    max_seq: maxSeq,
    events: [...seqs].sort((a, b) => b - a).map(event),
  };
}

const fetchMock = vi.fn();

function requestedUrl(index: number): URL {
  return new URL(fetchMock.mock.calls[index]![0] as string);
}

function renderStore() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useEventStore(undefined, { refetchInterval: false }), { wrapper });
}

describe("useEventStore", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function respond(...bodies: object[]) {
    for (const body of bodies) {
      fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => body });
    }
  }

  it("loads the whole store on first fetch and follows it with a delta", async () => {
    respond(page("e:0", 2, [1, 2]), page("e:0", 4, [3, 4]));
    const { result } = renderStore();
    await waitFor(() => expect(result.current.data).toBeDefined());

    await result.current.refetch();

    await waitFor(() => expect(result.current.data?.maxSeq).toBe(4));
    expect(result.current.data?.events.map((e) => e.seq)).toEqual([4, 3, 2, 1]);
    expect(requestedUrl(0).searchParams.get("after_seq")).toBeNull();
    expect(requestedUrl(1).searchParams.get("after_seq")).toBe("2");
  });

  it("keeps array identity when the delta is empty", async () => {
    respond(page("e:0", 2, [1, 2]), page("e:0", 2, []));
    const { result } = renderStore();
    await waitFor(() => expect(result.current.data).toBeDefined());
    const before = result.current.data!.events;

    await result.current.refetch();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(result.current.data!.events).toBe(before);
  });

  it("resyncs from scratch when the epoch changes", async () => {
    respond(page("e:0", 2, [1, 2]), page("e:1", 1, [1]), page("e:1", 1, [1]));
    const { result } = renderStore();
    await waitFor(() => expect(result.current.data).toBeDefined());

    await result.current.refetch();

    await waitFor(() => expect(result.current.data?.epoch).toBe("e:1"));
    expect(result.current.data?.events.map((e) => e.seq)).toEqual([1]);
    // The third request is the full resync — no cursor.
    expect(requestedUrl(2).searchParams.get("after_seq")).toBeNull();
  });

  it("keeps paging when a delta is truncated by the limit", async () => {
    // max_seq 6 with only seqs 3-4 returned means the page was cut short.
    respond(page("e:0", 2, [1, 2]), page("e:0", 6, [3, 4]), page("e:0", 6, [5, 6]));
    const { result } = renderStore();
    await waitFor(() => expect(result.current.data).toBeDefined());

    await result.current.refetch();

    await waitFor(() => expect(result.current.data?.maxSeq).toBe(6));
    expect(result.current.data?.events.map((e) => e.seq)).toEqual([6, 5, 4, 3, 2, 1]);
    expect(requestedUrl(2).searchParams.get("after_seq")).toBe("4");
  });

  it("resyncs when max_seq drops below the cursor", async () => {
    // Rows removed out of band — another process, a manual delete, a VACUUM —
    // none of which bump the epoch, but all of which void the cursor.
    respond(page("e:0", 5, [4, 5]), page("e:0", 2, []), page("e:0", 2, [1, 2]));
    const { result } = renderStore();
    await waitFor(() => expect(result.current.data?.maxSeq).toBe(5));

    await result.current.refetch();

    await waitFor(() => expect(result.current.data?.maxSeq).toBe(2));
    expect(result.current.data?.events.map((e) => e.seq)).toEqual([2, 1]);
    expect(requestedUrl(2).searchParams.get("after_seq")).toBeNull();
  });
});
