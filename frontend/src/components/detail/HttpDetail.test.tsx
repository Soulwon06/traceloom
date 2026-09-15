import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EventDetail, HttpEventData } from "../../api/events";
import HttpDetail from "./HttpDetail";

describe("HttpDetail", () => {
  it("shows the operation error when a request has no response", () => {
    const detail: EventDetail & { data: HttpEventData } = {
      id: "550e8400-e29b-41d4-a716-446655440000",
      seq: 0,
      timestamp: "2026-08-02T12:00:00Z",
      event_type: "http",
      summary: "POST /v1/charges → ConnectTimeout",
      app: "",
      session: "",
      hierarchy: null,
      data: {
        event_type: "http",
        app: "",
        session: "",
        duration_ms: 5001,
        method: "POST",
        url: "https://api.stripe.com/v1/charges",
        host: "api.stripe.com",
        request_headers: {},
        request_body: null,
        request_body_size: 0,
        status_code: null,
        response_headers: {},
        response_body: null,
        response_body_size: 0,
        error: {
          type: "ConnectTimeout",
          message: "connection timed out",
          module: "httpx",
        },
        library: "httpx",
        python_version: "3.14.0",
        traceloom_version: "0.15.0",
      },
    };

    render(<HttpDetail detail={detail} />);

    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("ConnectTimeout")).toBeInTheDocument();
    expect(within(alert).getByText("connection timed out")).toBeInTheDocument();
    expect(within(alert).getByText("httpx")).toBeInTheDocument();
    expect(screen.getAllByText("Headers (0)")).toHaveLength(2);
  });
});
