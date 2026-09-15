import type { EventSummary } from "../api/events";

export const groupingDefinitions = {
  pytest: [
    { key: "test_directory", label: "Test directory" },
    { key: "test_file", label: "Test file" },
    { key: "test_class", label: "Test class" },
    { key: "test_case", label: "Test case" },
  ],
  http_request: [{ key: "hostname", label: "Remote host" }],
} as const;

export type PytestGroupingKey = (typeof groupingDefinitions.pytest)[number]["key"];
export type GroupingMode = "none" | `pytest:${PytestGroupingKey}` | "http_request:hostname";

export interface GroupingOption {
  value: GroupingMode;
  label: string;
}

export function availableGroupingOptions(events: EventSummary[]): GroupingOption[] {
  const options: GroupingOption[] = [{ value: "none", label: "None" }];
  const pytestKeys = new Set<PytestGroupingKey>();
  let hasHttpRequest = false;

  for (const event of events) {
    for (const membership of event.hierarchy?.group_memberships ?? []) {
      if (membership.kind === "http_request") {
        hasHttpRequest = true;
      } else {
        for (const definition of groupingDefinitions.pytest) {
          if (membership[definition.key]) pytestKeys.add(definition.key);
        }
      }
    }
  }

  for (const definition of groupingDefinitions.pytest) {
    if (pytestKeys.has(definition.key)) {
      options.push({
        value: `pytest:${definition.key}`,
        label: definition.label,
      });
    }
  }
  if (hasHttpRequest) {
    options.push({ value: "http_request:hostname", label: "Remote host" });
  }
  return options;
}
