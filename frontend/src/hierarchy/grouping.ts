import type { EventSummary } from "../api/events";
import { groupingDefinitions, type GroupingMode, type PytestGroupingKey } from "./definitions";
import { buildRuntimeTree, type RuntimeTreeNode } from "./runtimeTree";

type GroupReference = { id: string; label: string };

export interface MembershipGroupNode {
  kind: "group";
  id: string;
  label: string;
  referenceId: string;
  children: HierarchyNode[];
}

export interface OperationNode extends Omit<RuntimeTreeNode, "children"> {
  children: HierarchyNode[];
}

export interface EventNode {
  kind: "event";
  id: string;
  event: EventSummary;
}

export type HierarchyNode = MembershipGroupNode | OperationNode | EventNode;

export interface HierarchyProjection {
  nodes: HierarchyNode[];
}

type SourceNode =
  | { kind: "operation"; node: RuntimeTreeNode }
  | { kind: "event"; event: EventSummary };

function pytestPath(event: EventSummary, selectedKey: PytestGroupingKey): GroupReference[] | null {
  const membership = event.hierarchy?.group_memberships.find((item) => item.kind === "pytest");
  if (!membership) return null;

  const selectedIndex = groupingDefinitions.pytest.findIndex(
    (definition) => definition.key === selectedKey,
  );
  const path: GroupReference[] = [];
  for (const definition of groupingDefinitions.pytest.slice(0, selectedIndex + 1)) {
    const reference = membership[definition.key];
    if (reference) path.push(reference);
  }
  return membership[selectedKey] && path.length > 0 ? path : null;
}

function membershipPath(event: EventSummary, mode: GroupingMode): GroupReference[] | null {
  if (mode === "none") return null;
  if (mode.startsWith("pytest:")) {
    return pytestPath(event, mode.slice("pytest:".length) as PytestGroupingKey);
  }
  if (mode === "http_request:hostname") {
    const membership = event.hierarchy?.group_memberships.find(
      (item) => item.kind === "http_request",
    );
    return membership ? [membership.hostname] : null;
  }
  return null;
}

export function buildHierarchyProjection(
  events: EventSummary[],
  mode: GroupingMode,
): HierarchyProjection {
  const runtime = buildRuntimeTree(events);
  const order = new Map(events.map((event, index) => [event.id, index]));
  const sources: SourceNode[] = [
    ...runtime.roots.map((node): SourceNode => ({ kind: "operation", node })),
    ...runtime.uncorrelated.map((event): SourceNode => ({ kind: "event", event })),
  ];
  sources.sort((left, right) => sourceOrder(left, order) - sourceOrder(right, order));

  return { nodes: projectSequence(sources, [], "root", mode) };
}

function projectSequence(
  sources: SourceNode[],
  activePath: GroupReference[],
  scope: string,
  mode: GroupingMode,
): HierarchyNode[] {
  const result: HierarchyNode[] = [];

  for (const source of sources) {
    const event = source.kind === "operation" ? source.node.event : source.event;
    const ownPath = membershipPath(event, mode);
    const effectivePath = ownPath ?? activePath;
    const insertionPath = ownPath ? pathAfterCommonPrefix(activePath, ownPath) : [];
    const node =
      source.kind === "operation"
        ? projectOperation(source.node, effectivePath, mode)
        : ({ kind: "event", id: `event:${source.event.id}`, event: source.event } as const);

    appendWithGroups(result, insertionPath, node, scope, mode);
  }

  return result;
}

function projectOperation(
  node: RuntimeTreeNode,
  activePath: GroupReference[],
  mode: GroupingMode,
): OperationNode {
  const childSources = node.children.map(
    (child): SourceNode => ({ kind: "operation", node: child }),
  );
  return {
    ...node,
    children: projectSequence(childSources, activePath, node.id, mode),
  };
}

function pathAfterCommonPrefix(
  parentPath: GroupReference[],
  childPath: GroupReference[],
): GroupReference[] {
  let commonLength = 0;
  while (
    commonLength < parentPath.length &&
    commonLength < childPath.length &&
    parentPath[commonLength]!.id === childPath[commonLength]!.id
  ) {
    commonLength += 1;
  }
  return childPath.slice(commonLength);
}

function appendWithGroups(
  siblings: HierarchyNode[],
  path: GroupReference[],
  node: HierarchyNode,
  scope: string,
  mode: GroupingMode,
): void {
  let destination = siblings;
  const traversed: GroupReference[] = [];
  const traversedGroups: Array<{ group: MembershipGroupNode; pathId: string }> = [];

  for (const reference of path) {
    traversed.push(reference);
    const pathId = traversed.map((part) => encodeURIComponent(part.id)).join("/");
    const previous = destination[destination.length - 1];
    let group =
      previous?.kind === "group" && previous.referenceId === reference.id ? previous : undefined;
    if (!group) {
      group = {
        kind: "group",
        id: `group:${mode}:${encodeURIComponent(scope)}:${pathId}:${encodeURIComponent(node.id)}`,
        label: reference.label,
        referenceId: reference.id,
        children: [],
      };
      destination.push(group);
    }
    traversedGroups.push({ group, pathId });
    destination = group.children;
  }

  destination.push(node);
  for (const { group, pathId } of traversedGroups) {
    group.id = `group:${mode}:${encodeURIComponent(scope)}:${pathId}:${encodeURIComponent(node.id)}`;
  }
}

function sourceOrder(source: SourceNode, order: Map<string, number>): number {
  const event = source.kind === "operation" ? source.node.event : source.event;
  return order.get(event.id) ?? Number.MAX_SAFE_INTEGER;
}

export function countHierarchyEvents(node: HierarchyNode): number {
  if (node.kind === "event") return 1;
  if (node.kind === "operation") {
    return (
      1 +
      node.annotations.length +
      node.children.reduce((total, child) => total + countHierarchyEvents(child), 0)
    );
  }
  return node.children.reduce((total, child) => total + countHierarchyEvents(child), 0);
}
