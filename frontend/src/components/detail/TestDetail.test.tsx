import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EventDetail, TestEventData } from "../../api/events";
import TestDetail from "./TestDetail";

const testData: TestEventData = {
  event_type: "test",
  app: "",
  session: "",
  framework: "pytest",
  framework_version: "9.0.2",
  python_version: "3.14.0",
  traceloom_version: "0.14.1",
  run_id: "run-123",
  worker_id: "gw0",
  test_id: "tests/test_checkout.py::test_total[usd]",
  name: "test_total[usd]",
  path: "tests/test_checkout.py",
  line: 42,
  status: "failed",
  duration_ms: 18.75,
  setup_duration_ms: 5.25,
  call_duration_ms: 12.5,
  teardown_duration_ms: 1,
  fixtures: ["currency", "db"],
  failures: [
    {
      phase: "call",
      exception_type: "AssertionError",
      message: "assert 9 == 10",
      traceback_text: "tests/test_checkout.py:43: AssertionError",
    },
  ],
};

const detail: EventDetail & { data: TestEventData } = {
  id: "test-123",
  seq: 0,
  timestamp: "2026-07-27T10:00:00Z",
  event_type: "test",
  summary: "FAILED tests/test_checkout.py::test_total[usd]",
  app: "",
  session: "",
  data: testData,
};

describe("TestDetail", () => {
  it("renders timing, fixtures, and failure details", () => {
    render(<TestDetail detail={detail} />);

    expect(screen.getByText("FAILED")).toBeInTheDocument();
    expect(screen.getByText("test_total[usd]")).toBeInTheDocument();
    expect(screen.getByText("tests/test_checkout.py::test_total[usd]")).toBeInTheDocument();
    expect(screen.getByText("18.8 ms")).toBeInTheDocument();
    expect(screen.getByText("currency")).toBeInTheDocument();
    expect(screen.getByText("db")).toBeInTheDocument();
    expect(screen.getByText("AssertionError")).toBeInTheDocument();
    expect(screen.getByText("assert 9 == 10")).toBeInTheDocument();
    expect(screen.getByText("tests/test_checkout.py:43: AssertionError")).toBeInTheDocument();
  });
});
