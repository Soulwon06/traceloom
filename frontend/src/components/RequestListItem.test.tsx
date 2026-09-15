import { render, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import RequestListItem from "./RequestListItem";
import type { EventSummary } from "../api/events";

const httpItem: EventSummary = {
  id: "abc-123",
  seq: 0,
  timestamp: "2025-01-15T14:30:45.123Z",
  event_type: "http",
  summary: "GET /users?page=1 → 200",
  app: "",
  session: "",
};

const logItem: EventSummary = {
  id: "log-123",
  seq: 0,
  timestamp: "2025-01-15T14:30:45.123Z",
  event_type: "log",
  summary: "WARNING myapp.auth: Token expired for user 42",
  app: "",
  session: "",
};

const exceptionItem: EventSummary = {
  id: "exc-123",
  seq: 0,
  timestamp: "2025-01-15T14:30:45.123Z",
  event_type: "exception",
  summary: "ValueError: invalid literal for int()",
  app: "",
  session: "",
};

const testItem: EventSummary = {
  id: "test-123",
  seq: 0,
  timestamp: "2025-01-15T14:30:45.123Z",
  event_type: "test",
  summary: "FAILED tests/test_checkout.py::test_total[usd]",
  app: "",
  session: "",
};

function renderItem(item: EventSummary, onClick = () => {}) {
  const { container } = render(<RequestListItem item={item} selected={false} onClick={onClick} />);
  return within(container);
}

describe("RequestListItem", () => {
  it("renders HTTP event with method and path", () => {
    const view = renderItem(httpItem);
    expect(view.getByText("GET")).toBeInTheDocument();
    expect(view.getByText("/users?page=1")).toBeInTheDocument();
    expect(view.getByText("200")).toBeInTheDocument();
  });

  it("renders a failed HTTP event with its error outcome", () => {
    const view = renderItem({
      ...httpItem,
      summary: "POST /charge → ConnectionError",
    });

    expect(view.getByText("POST")).toBeInTheDocument();
    expect(view.getByText("/charge")).toBeInTheDocument();
    expect(view.getByText("ConnectionError")).toBeInTheDocument();
    expect(view.queryByText("???")).not.toBeInTheDocument();
    expect(view.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders log event with level and message", () => {
    const view = renderItem(logItem);
    expect(view.getByText("WARNING")).toBeInTheDocument();
    expect(view.getByText("Token expired for user 42")).toBeInTheDocument();
    expect(view.getByText("myapp.auth")).toBeInTheDocument();
  });

  it("renders exception event with type", () => {
    const view = renderItem(exceptionItem);
    expect(view.getByText("ValueError")).toBeInTheDocument();
  });

  it("renders test function before its path", () => {
    const view = renderItem(testItem);
    expect(view.getByText("FAILED")).toBeInTheDocument();
    expect(view.getByText("test_total[usd]")).toBeInTheDocument();
    expect(view.getByText("tests/test_checkout.py")).toBeInTheDocument();
  });

  it("keeps class context with the test path", () => {
    const item = {
      ...testItem,
      summary: "PASSED tests/test_checkout.py::TestCheckout::test_total[usd]",
    };
    const view = renderItem(item);

    expect(view.getByText("test_total[usd]")).toBeInTheDocument();
    expect(view.getByText("tests/test_checkout.py::TestCheckout")).toBeInTheDocument();
  });

  it("formats timestamp as HH:MM:SS in 24-hour format", () => {
    const view = renderItem(httpItem);
    const timeSpan = view.getByText(/^\d{2}:\d{2}:\d{2}$/);
    expect(timeSpan).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    const view = renderItem(httpItem, onClick);
    view.getByRole("button").click();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("shows app label when app is set", () => {
    const item = { ...httpItem, app: "myapp" };
    const view = renderItem(item);
    expect(view.getByText("· myapp")).toBeInTheDocument();
  });

  it("hides app label when app is empty", () => {
    const view = renderItem(httpItem);
    expect(view.queryByText(/^·/)).not.toBeInTheDocument();
  });
});
