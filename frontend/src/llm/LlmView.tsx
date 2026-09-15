import JsonView from "react18-json-view";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { customizeNode } from "../annotations";
import { mono } from "../theme";
import TermExplanation from "../components/TermExplanation";
import type { LlmBlock, LlmMessage, LlmRole, LlmView as LlmViewModel } from "./types";

const roleStyles: Record<LlmRole, { title: string; english: string; color: string; bg: string }> = {
  system: {
    title: "系统指令",
    english: "System Prompt",
    color: "#6d4c41",
    bg: "transparent",
  },
  user: {
    title: "用户输入",
    english: "User",
    color: "#1976d2",
    bg: "transparent",
  },
  assistant: {
    title: "模型回复",
    english: "Assistant",
    color: "#2e7d32",
    bg: "transparent",
  },
  tool: {
    title: "工具",
    english: "Tool",
    color: "#7b1fa2",
    bg: "transparent",
  },
};

const textSx = {
  fontSize: 13,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  m: 0,
} as const;

const providerLabels: Record<LlmViewModel["provider"], string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
};

const finishReasonLabels: Record<string, string> = {
  stop: "正常停止",
  end_turn: "结束本轮",
  completed: "已完成",
  tool_calls: "请求调用工具",
  tool_use: "使用工具",
};

function TokenMetric({
  value,
  title,
  english,
}: {
  value?: number;
  title: string;
  english: string;
}) {
  if (value === undefined) return null;

  return (
    <Box sx={{ minWidth: 72 }}>
      <Typography
        sx={{
          fontFamily: mono,
          fontSize: 18,
          lineHeight: 1.2,
          fontWeight: 600,
          color: "text.primary",
        }}
      >
        {value}
      </Typography>
      <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.25 }}>
        {title} {english}
      </Typography>
    </Box>
  );
}

function TokenUsage({ usage }: { usage: NonNullable<LlmViewModel["usage"]> }) {
  const secondaryParts: string[] = [];

  if (usage.thinkingTokens !== undefined) {
    secondaryParts.push(`${usage.thinkingTokens} thinking`);
  }

  if (usage.cacheReadTokens !== undefined) {
    secondaryParts.push(`${usage.cacheReadTokens} cache read`);
  }

  if (usage.cacheWriteTokens !== undefined) {
    secondaryParts.push(`${usage.cacheWriteTokens} cache write`);
  }

  return (
    <Box sx={{ pt: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={{ xs: 1, sm: 3 }}
        alignItems={{ xs: "flex-start", sm: "center" }}
      >
        <TermExplanation
          title="Token 用量"
          english="Token Usage"
          what="表示模型处理输入内容和生成输出内容时使用的文本计量。"
          why="可以帮助你理解一次 LLM 调用的输入输出规模，并辅助观察上下文是否过长。"
          how="如果 Input Token 明显增加，可以检查 System Prompt、历史对话或额外 Context；如果 Output Token 较高，可以检查模型是否生成了过长内容。"
        />

        <Stack direction="row" spacing={3} sx={{ flexWrap: "wrap", rowGap: 1 }}>
          <TokenMetric value={usage.inputTokens} title="输入" english="Input" />
          <TokenMetric value={usage.outputTokens} title="输出" english="Output" />
        </Stack>
      </Stack>

      {secondaryParts.length > 0 && (
        <Typography
          sx={{
            fontFamily: mono,
            fontSize: 11,
            color: "text.secondary",
            mt: 1,
          }}
        >
          {secondaryParts.join(" · ")}
        </Typography>
      )}
    </Box>
  );
}

function FinishReason({ reason }: { reason: string }) {
  const displayLabel = finishReasonLabels[reason];

  return (
    <Box sx={{ pt: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={{ xs: 1, sm: 3 }}
        alignItems={{ xs: "flex-start", sm: "center" }}
      >
        <TermExplanation
          title="结束原因"
          english="Finish Reason"
          what="表示模型为什么结束本次生成。"
          why="可以帮助判断一次生成是正常完成、触发工具调用，还是因为其他条件结束。"
          how="如果结束原因与预期不一致，可以结合回复内容、工具调用和原始响应继续检查。"
        />

        <Stack direction="row" spacing={1.25} alignItems="baseline" sx={{ flexWrap: "wrap" }}>
          <Typography sx={{ fontSize: 14, color: "text.primary" }}>
            {displayLabel ?? reason}
          </Typography>
          {displayLabel && (
            <Typography sx={{ fontFamily: mono, fontSize: 12, color: "text.secondary" }}>
              {reason}
            </Typography>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}

function JsonBox({ src }: { src: unknown }) {
  if (typeof src === "string") {
    return (
      <Typography
        component="pre"
        sx={{
          ...textSx,
          fontFamily: mono,
          color: "text.primary",
        }}
      >
        {src}
      </Typography>
    );
  }

  return (
    <Box sx={{ fontSize: 12, fontFamily: mono }}>
      <JsonView src={src} collapsed={1} customizeNode={customizeNode} />
    </Box>
  );
}

function BlockView({ block }: { block: LlmBlock }) {
  switch (block.kind) {
    case "text":
      return (
        <Typography component="pre" sx={textSx}>
          {block.text}
        </Typography>
      );

    case "thinking":
      return (
        <Stack spacing={0.75}>
          <TermExplanation
            title="思考过程"
            english="Thinking"
            what="表示当前 Provider/API 返回并允许展示的推理或思考相关内容。"
            why="在支持该信息的模型中，它可以辅助理解模型生成答案前暴露出的部分推理信息。"
            how="可以将它作为调试参考，但不要把它视为模型全部或完整的内部推理过程。"
          />
          <Typography
            component="pre"
            sx={{
              ...textSx,
              fontStyle: "italic",
              color: "text.secondary",
            }}
          >
            {block.text}
          </Typography>
        </Stack>
      );

    case "image":
      return (
        <Chip
          label={block.media ? `图片 Image (${block.media})` : "图片 Image"}
          size="small"
          variant="outlined"
          sx={{
            fontSize: 11,
            height: 22,
            color: "text.secondary",
            borderColor: "divider",
          }}
        />
      );

    case "tool_use":
      return (
        <Box
          sx={{
            pl: 1,
            borderLeft: "2px solid",
            borderColor: "rgba(123,31,162,0.32)",
          }}
        >
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={0.75}
            alignItems={{ xs: "flex-start", sm: "center" }}
            sx={{ mb: 0.75 }}
          >
            <TermExplanation
              title="工具调用"
              english="Tool Use"
              what="表示模型请求调用外部工具或函数来完成某个操作。"
              why="可以帮助理解模型是否把任务交给了正确的工具，以及调用发生在对话的哪个位置。"
              how="如果工具执行结果与预期不一致，可以继续检查工具名称、参数和返回结果。"
            />
            <Typography
              sx={{
                fontSize: 11,
                fontWeight: 700,
                color: "#7b1fa2",
              }}
            >
              → {block.name || "tool"}
            </Typography>

            {block.id && (
              <Typography
                sx={{
                  fontFamily: mono,
                  fontSize: 11,
                  color: "text.disabled",
                }}
              >
                {block.id}
              </Typography>
            )}
          </Stack>

          <JsonBox src={block.input} />
        </Box>
      );

    case "tool_result": {
      const color = block.isError ? "#d32f2f" : "#2e7d32";

      return (
        <Box
          sx={{
            pl: 1,
            borderLeft: "2px solid",
            borderColor: block.isError ? "rgba(211,47,47,0.38)" : "rgba(46,125,50,0.32)",
          }}
        >
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={0.75}
            alignItems={{ xs: "flex-start", sm: "center" }}
            sx={{ mb: 0.75 }}
          >
            <TermExplanation
              title="工具结果"
              english="Tool Result"
              what="表示外部工具执行后返回给模型的结果。"
              why="模型后续回答通常会依赖这个结果，因此它是排查工具调用链的重要信息。"
              how="如果最终回答异常，可以检查工具返回的数据是否完整、格式是否符合预期。"
            />
            <Typography sx={{ fontSize: 11, fontWeight: 700, color }}>
              ← tool result{block.isError ? " (error)" : ""}
            </Typography>
          </Stack>

          <JsonBox src={block.content} />
        </Box>
      );
    }

    case "unknown":
      return <JsonBox src={block.raw} />;

    default: {
      const _exhaustive: never = block;
      void _exhaustive;
      return null;
    }
  }
}

function MessageView({ message }: { message: LlmMessage }) {
  const style = roleStyles[message.role];

  return (
    <Box
      sx={{
        borderLeft: "3px solid",
        borderColor: style.color,
        bgcolor: style.bg,
        borderRadius: "0 4px 4px 0",
        px: 1.5,
        py: 1,
      }}
    >
      {message.role === "system" ? (
        <TermExplanation
          title="系统指令"
          english="System Prompt"
          what="用于给模型设定角色、行为规则和回答约束的指令。"
          why="System Prompt 会直接影响模型的回答方式，并占用输入上下文。"
          how="如果模型的回答风格、格式或行为与预期不一致，可以检查 System Prompt 是否存在冲突、冗余或过强约束。"
        />
      ) : (
        <>
          <Typography
            sx={{
              fontSize: 11,
              fontWeight: 700,
              color: style.color,
              mb: 0.15,
            }}
          >
            {style.title}
          </Typography>
          <Typography sx={{ fontSize: 10, color: "text.secondary", mb: 0.75 }}>
            {style.english}
          </Typography>
        </>
      )}

      <Stack spacing={0.75}>
        {message.blocks.length ? (
          message.blocks.map((b, i) => <BlockView key={i} block={b} />)
        ) : (
          <Typography
            sx={{
              fontSize: 12,
              color: "text.disabled",
              fontStyle: "italic",
            }}
          >
            暂无内容 · Empty
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

export default function LlmView({ view }: { view: LlmViewModel }) {
  const systemBlocks = view.system ?? [];

  return (
    <Stack spacing={1.25}>
      <Box sx={{ pb: 1.5 }}>
        <Typography sx={{ fontSize: 16, fontWeight: 600, color: "text.primary" }}>
          LLM 调用
        </Typography>
        <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.25 }}>LLM Call</Typography>

        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={{ xs: 1.25, sm: 4 }}
          alignItems={{ xs: "flex-start", sm: "flex-end" }}
          sx={{ mt: 1.5, flexWrap: "wrap" }}
        >
          {view.model && (
            <Box>
              <Typography
                sx={{
                  fontFamily: mono,
                  fontSize: 18,
                  lineHeight: 1.2,
                  fontWeight: 600,
                  color: "text.primary",
                }}
              >
                {view.model}
              </Typography>
              <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.35 }}>
                模型 Model
              </Typography>
            </Box>
          )}

          <Box>
            <Typography
              sx={{ fontSize: 18, lineHeight: 1.2, fontWeight: 600, color: "text.primary" }}
            >
              {providerLabels[view.provider]}
            </Typography>
            <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.35 }}>
              服务商 Provider
            </Typography>
          </Box>
        </Stack>
      </Box>

      {view.stopReason && <FinishReason reason={view.stopReason} />}

      {view.usage && <TokenUsage usage={view.usage} />}

      {systemBlocks.length > 0 && (
        <MessageView
          message={{
            role: "system",
            blocks: systemBlocks,
          }}
        />
      )}

      {view.tools && view.tools.length > 0 && (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexWrap: "wrap" }}>
          <Typography
            sx={{
              fontSize: 11,
              fontWeight: 700,
              color: "text.secondary",
              mr: 0.5,
            }}
          >
            工具 Tools ({view.tools.length}):
          </Typography>

          {view.tools.map((t, i) => (
            <Tooltip
              key={i}
              title={t.description ?? ""}
              arrow
              disableHoverListener={!t.description}
            >
              <Chip
                label={t.name}
                size="small"
                variant="outlined"
                sx={{
                  fontFamily: mono,
                  fontSize: 11,
                  height: 20,
                  color: "text.secondary",
                  borderColor: "divider",
                }}
              />
            </Tooltip>
          ))}
        </Stack>
      )}

      {view.messages.map((m, i) => (
        <MessageView key={i} message={m} />
      ))}
    </Stack>
  );
}
