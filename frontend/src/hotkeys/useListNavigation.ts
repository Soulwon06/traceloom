import { useCallback, useMemo } from "react";
import { useAtom, useAtomValue } from "jotai";
import { useHotkeys } from "react-hotkeys-hook";
import { groupingModeAtom } from "../atoms/grouping";
import { collapsedHierarchyNodeIdsAtom } from "../atoms/hierarchy";
import { useSelectedRequestId } from "../hooks/useSelectedRequestId";
import { useFilteredRequests } from "../hooks/useFilteredRequests";
import { availableGroupingOptions } from "../hierarchy/definitions";
import { buildHierarchyProjection } from "../hierarchy/grouping";
import { buildHierarchyNavigation } from "../hierarchy/navigation";

export function useListNavigation() {
  const { data: requests = [] } = useFilteredRequests();
  const [selectedId, setSelectedId] = useSelectedRequestId();
  const groupingMode = useAtomValue(groupingModeAtom);
  const [collapsed, setCollapsed] = useAtom(collapsedHierarchyNodeIdsAtom);
  const effectiveMode = availableGroupingOptions(requests).some(
    (option) => option.value === groupingMode,
  )
    ? groupingMode
    : "none";
  const navigation = useMemo(
    () => buildHierarchyNavigation(buildHierarchyProjection(requests, effectiveMode), collapsed),
    [requests, effectiveMode, collapsed],
  );

  const navigate = useCallback(
    (direction: 1 | -1) => {
      const { visibleEventIds } = navigation;
      if (visibleEventIds.length === 0) return;
      const currentIndex = selectedId ? visibleEventIds.indexOf(selectedId) : -1;
      let nextIndex: number;
      if (currentIndex === -1 && selectedId) {
        const orderedIndex = navigation.orderedEventIds.indexOf(selectedId);
        const visibleIds = new Set(visibleEventIds);
        if (orderedIndex !== -1) {
          for (
            let index = orderedIndex + direction;
            index >= 0 && index < navigation.orderedEventIds.length;
            index += direction
          ) {
            const candidate = navigation.orderedEventIds[index]!;
            if (visibleIds.has(candidate)) {
              setSelectedId(candidate);
              return;
            }
          }
          return;
        }
        nextIndex = direction === 1 ? 0 : visibleEventIds.length - 1;
      } else if (currentIndex === -1) {
        nextIndex = direction === 1 ? 0 : visibleEventIds.length - 1;
      } else {
        nextIndex = currentIndex + direction;
        if (nextIndex < 0) nextIndex = 0;
        if (nextIndex >= visibleEventIds.length) nextIndex = visibleEventIds.length - 1;
      }
      setSelectedId(visibleEventIds[nextIndex]!);
    },
    [navigation, selectedId, setSelectedId],
  );

  const navigateRight = useCallback(() => {
    if (!selectedId) return;
    const operationNodeId = navigation.operationNodeIdByEventId.get(selectedId);
    if (!operationNodeId) return;

    if (collapsed.has(operationNodeId)) {
      setCollapsed((current) => {
        const next = new Set(current);
        next.delete(operationNodeId);
        return next;
      });
      return;
    }

    const firstChildId = navigation.firstChildEventIdByEventId.get(selectedId);
    if (firstChildId) setSelectedId(firstChildId);
  }, [collapsed, navigation, selectedId, setCollapsed, setSelectedId]);

  const navigateLeft = useCallback(() => {
    if (!selectedId) return;
    const operationNodeId = navigation.operationNodeIdByEventId.get(selectedId);
    const firstChildId = navigation.firstChildEventIdByEventId.get(selectedId);
    if (operationNodeId && firstChildId && !collapsed.has(operationNodeId)) {
      setCollapsed((current) => new Set(current).add(operationNodeId));
      return;
    }

    const parentId = navigation.parentEventIdByEventId.get(selectedId);
    if (parentId) setSelectedId(parentId);
  }, [collapsed, navigation, selectedId, setCollapsed, setSelectedId]);

  useHotkeys("j, ArrowDown", () => navigate(1), { preventDefault: true });
  useHotkeys("k, ArrowUp", () => navigate(-1), { preventDefault: true });
  useHotkeys("ArrowRight", navigateRight, { preventDefault: true });
  useHotkeys("ArrowLeft", navigateLeft, { preventDefault: true });
}
