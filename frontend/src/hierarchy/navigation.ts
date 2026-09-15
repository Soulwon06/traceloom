import type { HierarchyNode, HierarchyProjection, OperationNode } from "./grouping";

export interface HierarchyNavigation {
  orderedEventIds: string[];
  visibleEventIds: string[];
  operationNodeIdByEventId: Map<string, string>;
  parentEventIdByEventId: Map<string, string>;
  firstChildEventIdByEventId: Map<string, string>;
}

export function buildHierarchyNavigation(
  projection: HierarchyProjection,
  collapsed: ReadonlySet<string>,
): HierarchyNavigation {
  const orderedEventIds: string[] = [];
  const visibleEventIds: string[] = [];
  const operationNodeIdByEventId = new Map<string, string>();
  const parentEventIdByEventId = new Map<string, string>();
  const firstChildEventIdByEventId = new Map<string, string>();

  const collectEventIds = (node: HierarchyNode): void => {
    if (node.kind === "group") {
      for (const child of node.children) collectEventIds(child);
      return;
    }
    if (node.kind === "operation") {
      orderedEventIds.push(node.event.id);
      for (const annotation of node.annotations) orderedEventIds.push(annotation.id);
      for (const child of node.children) collectEventIds(child);
      return;
    }
    orderedEventIds.push(node.event.id);
  };

  const visitOperation = (node: OperationNode, parentEventId?: string): string => {
    const eventId = node.event.id;
    visibleEventIds.push(eventId);
    operationNodeIdByEventId.set(eventId, node.id);
    if (parentEventId) parentEventIdByEventId.set(eventId, parentEventId);

    if (collapsed.has(node.id)) return eventId;

    let firstChildEventId: string | undefined;
    for (const annotation of node.annotations) {
      visibleEventIds.push(annotation.id);
      parentEventIdByEventId.set(annotation.id, eventId);
      firstChildEventId ??= annotation.id;
    }
    for (const child of node.children) {
      const childFirstVisibleId = visitNode(child, eventId);
      firstChildEventId ??= childFirstVisibleId;
    }
    if (firstChildEventId) firstChildEventIdByEventId.set(eventId, firstChildEventId);
    return eventId;
  };

  const visitNode = (node: HierarchyNode, parentEventId?: string): string | undefined => {
    if (node.kind === "group") {
      if (collapsed.has(node.id)) return undefined;
      let firstVisibleId: string | undefined;
      for (const child of node.children) {
        const childFirstVisibleId = visitNode(child, parentEventId);
        firstVisibleId ??= childFirstVisibleId;
      }
      return firstVisibleId;
    }
    if (node.kind === "operation") return visitOperation(node, parentEventId);

    visibleEventIds.push(node.event.id);
    if (parentEventId) parentEventIdByEventId.set(node.event.id, parentEventId);
    return node.event.id;
  };

  for (const node of projection.nodes) {
    collectEventIds(node);
    visitNode(node);
  }

  return {
    orderedEventIds,
    visibleEventIds,
    operationNodeIdByEventId,
    parentEventIdByEventId,
    firstChildEventIdByEventId,
  };
}
