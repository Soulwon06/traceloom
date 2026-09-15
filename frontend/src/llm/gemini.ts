/**
 * Google Gemini GenerateContent API adapter.
 *
 * Parses native `contents` requests and `candidates` responses, including text,
 * thought, function-call, function-response, tool declaration, and usage data.
 */
import type { SseEvent } from "../components/SseViewer";
import type { LlmBlock, LlmMessage, LlmRole, LlmTool, LlmUsage, LlmView } from "./types";
import { asString, isRecord, numOrUndef, tryParseJson } from "./util";

function normalizeRole(role: unknown): LlmRole {
  if (role === "model") return "assistant";
  if (role === "function" || role === "tool") return "tool";
  return "user";
}

function partToBlock(part: unknown): LlmBlock {
  if (!isRecord(part)) return { kind: "unknown", raw: part };

  if (typeof part.text === "string") {
    return part.thought === true
      ? { kind: "thinking", text: part.text }
      : { kind: "text", text: part.text };
  }

  if (isRecord(part.functionCall)) {
    return {
      kind: "tool_use",
      name: asString(part.functionCall.name),
      id: asString(part.functionCall.id) || undefined,
      input: part.functionCall.args ?? {},
    };
  }

  if (isRecord(part.functionResponse)) {
    return {
      kind: "tool_result",
      toolUseId:
        asString(part.functionResponse.id) || asString(part.functionResponse.name) || undefined,
      content: part.functionResponse.response,
    };
  }

  const media = isRecord(part.inlineData)
    ? asString(part.inlineData.mimeType)
    : isRecord(part.fileData)
      ? asString(part.fileData.mimeType)
      : "";
  if (media.startsWith("image/")) return { kind: "image", media };

  return { kind: "unknown", raw: part };
}

function partsToBlocks(parts: unknown): LlmBlock[] {
  return Array.isArray(parts) ? parts.map(partToBlock) : [];
}

function contentToMessage(content: unknown): LlmMessage {
  if (!isRecord(content)) {
    return { role: "user", blocks: [{ kind: "unknown", raw: content }] };
  }
  const blocks = partsToBlocks(content.parts);
  const role =
    blocks.length > 0 && blocks.every((block) => block.kind === "tool_result")
      ? "tool"
      : normalizeRole(content.role);
  return {
    role,
    blocks,
  };
}

function systemOf(systemInstruction: unknown): LlmBlock[] | undefined {
  if (!isRecord(systemInstruction)) return undefined;
  const blocks = partsToBlocks(systemInstruction.parts);
  return blocks.length ? blocks : undefined;
}

function toolsOf(tools: unknown): LlmTool[] | undefined {
  if (!Array.isArray(tools)) return undefined;

  const declarations = tools.flatMap((tool) => {
    if (!isRecord(tool) || !Array.isArray(tool.functionDeclarations)) return [];
    return tool.functionDeclarations;
  });
  const mapped = declarations
    .filter(isRecord)
    .map((declaration) => ({
      name: asString(declaration.name),
      description: asString(declaration.description) || undefined,
    }))
    .filter((tool) => tool.name);
  return mapped.length ? mapped : undefined;
}

function usageOf(usage: unknown): LlmUsage | undefined {
  if (!isRecord(usage)) return undefined;
  const mapped: LlmUsage = {
    inputTokens: numOrUndef(usage.promptTokenCount),
    outputTokens: numOrUndef(usage.candidatesTokenCount),
    thinkingTokens: numOrUndef(usage.thoughtsTokenCount),
    cacheReadTokens: numOrUndef(usage.cachedContentTokenCount),
  };
  return Object.values(mapped).some((value) => value !== undefined) ? mapped : undefined;
}

function looksLikeContent(content: unknown): boolean {
  return isRecord(content) && Array.isArray(content.parts);
}

export function detectRequest(json: unknown): LlmView | null {
  if (!isRecord(json) || !Array.isArray(json.contents)) return null;
  if (!json.contents.length || !json.contents.every(looksLikeContent)) return null;

  const hasGeminiSignal =
    "systemInstruction" in json ||
    "generationConfig" in json ||
    "safetySettings" in json ||
    "tools" in json ||
    json.contents.some((content) => isRecord(content) && content.role === "model");
  if (!hasGeminiSignal) return null;

  return {
    provider: "gemini",
    kind: "request",
    system: systemOf(json.systemInstruction),
    messages: json.contents.map(contentToMessage),
    tools: toolsOf(json.tools),
  };
}

export function detectResponse(json: unknown): LlmView | null {
  if (!isRecord(json) || !Array.isArray(json.candidates) || !json.candidates.length) return null;
  if (!("modelVersion" in json || "usageMetadata" in json || "responseId" in json)) return null;

  const candidate = json.candidates[0];
  if (!isRecord(candidate) || !looksLikeContent(candidate.content)) return null;

  return {
    provider: "gemini",
    kind: "response",
    model: asString(json.modelVersion) || undefined,
    messages: [contentToMessage(candidate.content)],
    stopReason: asString(candidate.finishReason) || undefined,
    usage: usageOf(json.usageMetadata),
  };
}

function appendBlock(blocks: LlmBlock[], next: LlmBlock): void {
  const previous = blocks[blocks.length - 1];
  if (previous?.kind === "text" && next.kind === "text") {
    previous.text += next.text;
    return;
  }
  if (previous?.kind === "thinking" && next.kind === "thinking") {
    previous.text += next.text;
    return;
  }
  blocks.push(next);
}

export function detectStream(events: SseEvent[]): LlmView | null {
  const chunks = events
    .map((event) => (event.data ? tryParseJson(event.data) : null))
    .filter(isRecord);
  if (
    !chunks.some(
      (chunk) =>
        Array.isArray(chunk.candidates) &&
        chunk.candidates.some(
          (candidate) => isRecord(candidate) && looksLikeContent(candidate.content),
        ),
    )
  ) {
    return null;
  }

  let model: string | undefined;
  let stopReason: string | undefined;
  let usage: LlmUsage | undefined;
  const blocks: LlmBlock[] = [];

  for (const chunk of chunks) {
    model = asString(chunk.modelVersion) || model;
    usage = usageOf(chunk.usageMetadata) ?? usage;
    if (!Array.isArray(chunk.candidates)) continue;
    const candidate = chunk.candidates[0];
    if (!isRecord(candidate)) continue;
    stopReason = asString(candidate.finishReason) || stopReason;
    if (!isRecord(candidate.content)) continue;
    for (const block of partsToBlocks(candidate.content.parts)) appendBlock(blocks, block);
  }

  return {
    provider: "gemini",
    kind: "response",
    model,
    messages: [{ role: "assistant", blocks }],
    stopReason,
    usage,
  };
}
