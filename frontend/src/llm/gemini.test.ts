import { describe, expect, it } from "vitest";
import type { SseEvent } from "../components/SseViewer";
import { detectRequest, detectResponse, detectStream } from "./gemini";

function sse(data: unknown): SseEvent {
  return { data: JSON.stringify(data), comments: [] };
}

describe("gemini.detectRequest", () => {
  it("parses contents, system instructions, tools, and function traffic", () => {
    const view = detectRequest({
      systemInstruction: { parts: [{ text: "Be concise." }] },
      contents: [
        { role: "user", parts: [{ text: "How is traffic?" }] },
        {
          role: "model",
          parts: [{ functionCall: { name: "run_report", args: { metric: "sessions" } } }],
        },
        {
          role: "user",
          parts: [
            {
              functionResponse: {
                name: "run_report",
                response: { sessions: 42 },
              },
            },
          ],
        },
      ],
      tools: [
        {
          functionDeclarations: [{ name: "run_report", description: "Run an analytics report" }],
        },
      ],
      generationConfig: { temperature: 0.2 },
    });

    expect(view).not.toBeNull();
    expect(view!.provider).toBe("gemini");
    expect(view!.kind).toBe("request");
    expect(view!.system).toEqual([{ kind: "text", text: "Be concise." }]);
    expect(view!.tools).toEqual([{ name: "run_report", description: "Run an analytics report" }]);
    expect(view!.messages).toEqual([
      { role: "user", blocks: [{ kind: "text", text: "How is traffic?" }] },
      {
        role: "assistant",
        blocks: [
          {
            kind: "tool_use",
            name: "run_report",
            id: undefined,
            input: { metric: "sessions" },
          },
        ],
      },
      {
        role: "tool",
        blocks: [
          {
            kind: "tool_result",
            toolUseId: "run_report",
            content: { sessions: 42 },
          },
        ],
      },
    ]);
  });

  it("does not claim an unrelated contents payload", () => {
    expect(detectRequest({ contents: [{ parts: [{ text: "hello" }] }] })).toBeNull();
  });
});

describe("gemini.detectResponse", () => {
  it("parses model output, thinking, function calls, and usage", () => {
    const view = detectResponse({
      candidates: [
        {
          content: {
            role: "model",
            parts: [
              { text: "I should inspect the report.", thought: true },
              {
                functionCall: {
                  name: "emit_markdown",
                  args: { content: "Traffic is up." },
                },
                thoughtSignature: "opaque",
              },
            ],
          },
          finishReason: "STOP",
        },
      ],
      usageMetadata: {
        promptTokenCount: 100,
        candidatesTokenCount: 12,
        thoughtsTokenCount: 3,
        cachedContentTokenCount: 20,
      },
      modelVersion: "gemini-3.5-flash",
      responseId: "response-1",
    });

    expect(view).not.toBeNull();
    expect(view!.provider).toBe("gemini");
    expect(view!.model).toBe("gemini-3.5-flash");
    expect(view!.stopReason).toBe("STOP");
    expect(view!.usage).toEqual({
      inputTokens: 100,
      outputTokens: 12,
      thinkingTokens: 3,
      cacheReadTokens: 20,
    });
    expect(view!.messages).toEqual([
      {
        role: "assistant",
        blocks: [
          { kind: "thinking", text: "I should inspect the report." },
          {
            kind: "tool_use",
            name: "emit_markdown",
            id: undefined,
            input: { content: "Traffic is up." },
          },
        ],
      },
    ]);
  });

  it("returns null for an unrelated candidates payload", () => {
    expect(detectResponse({ candidates: [{ score: 0.9 }] })).toBeNull();
  });
});

describe("gemini.detectStream", () => {
  it("reassembles streamed text and usage", () => {
    const view = detectStream([
      sse({
        candidates: [{ content: { role: "model", parts: [{ text: "Hel" }] } }],
        modelVersion: "gemini-3.5-flash",
      }),
      sse({
        candidates: [
          {
            content: { role: "model", parts: [{ text: "lo" }] },
            finishReason: "STOP",
          },
        ],
        usageMetadata: { promptTokenCount: 8, candidatesTokenCount: 2 },
      }),
    ]);

    expect(view).not.toBeNull();
    expect(view!.model).toBe("gemini-3.5-flash");
    expect(view!.messages).toEqual([
      { role: "assistant", blocks: [{ kind: "text", text: "Hello" }] },
    ]);
    expect(view!.usage).toEqual({
      inputTokens: 8,
      outputTokens: 2,
      thinkingTokens: undefined,
      cacheReadTokens: undefined,
    });
  });
});
