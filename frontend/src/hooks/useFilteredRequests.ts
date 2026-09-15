import { useMemo } from "react";
import { useAtomValue } from "jotai";
import {
  hostFilterAtom,
  methodFilterAtom,
  searchFilterAtom,
  eventTypeFilterAtom,
  appFilterAtom,
  sessionFilterAtom,
} from "../atoms/filters";
import { useEventIds, useEventStore, useSearchEvents, type EventSummary } from "../api/events";

/**
 * The event list the timeline renders.
 *
 * The store already holds every event for the selected session, so structural
 * filters run locally — which also means every runtime ancestor of a match is
 * present without asking the server for one. Only `search` goes back out: it
 * matches against request and response bodies the browser never loads, so the
 * server returns the matching IDs and we intersect.
 *
 * That intersection is only sound while the store holds every candidate. It
 * does not when the store hit its page limit — a search can then match events
 * older than the store's floor, and intersecting would drop them without a
 * word. In that case we fall back to fetching the matches themselves.
 */
export function useFilteredRequests(): { data: EventSummary[]; isLoading: boolean } {
  const host = useAtomValue(hostFilterAtom);
  const method = useAtomValue(methodFilterAtom);
  const search = useAtomValue(searchFilterAtom);
  const eventType = useAtomValue(eventTypeFilterAtom);
  const app = useAtomValue(appFilterAtom);
  const session = useAtomValue(sessionFilterAtom);

  const { data: store, isLoading } = useEventStore(session);

  const searchParams = useMemo(
    () => ({
      search,
      ...(eventType ? { event_type: eventType } : {}),
      ...(host ? { host } : {}),
      ...(method ? { method } : {}),
      ...(app !== undefined ? { app } : {}),
      ...(session !== undefined ? { session } : {}),
    }),
    [search, eventType, host, method, app, session],
  );
  const { data: searchResult } = useEventIds(searchParams, {
    enabled: search !== "",
    refetchInterval: 3_000,
  });

  const events = store?.events;
  const loadedIds = useMemo(() => new Set((events ?? []).map((event) => event.id)), [events]);
  const missesLoadedEvents =
    search !== "" && (searchResult?.ids ?? []).some((id) => !loadedIds.has(id));
  const { data: searchEvents } = useSearchEvents(searchParams, {
    enabled: missesLoadedEvents,
    refetchInterval: 3_000,
  });

  const data = useMemo(() => {
    if (missesLoadedEvents) return searchEvents?.events ?? [];
    if (!events) return [];
    const matchedIds = search === "" ? null : new Set(searchResult?.ids ?? []);
    if (matchedIds === null && !eventType && !host && !method && app === undefined) {
      return events;
    }
    return events.filter(
      (event) =>
        (!eventType || event.event_type === eventType) &&
        (!host || event.host === host) &&
        (!method || event.method === method) &&
        (app === undefined || event.app === app) &&
        (matchedIds === null || matchedIds.has(event.id)),
    );
  }, [
    events,
    eventType,
    host,
    method,
    app,
    search,
    searchResult,
    missesLoadedEvents,
    searchEvents,
  ]);

  return { data, isLoading };
}
