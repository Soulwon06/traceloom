import { useEffect, useRef } from "react";
import ListItemButton from "@mui/material/ListItemButton";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { mono, neutral } from "../theme";
import StatusBadge from "./StatusBadge";
import EventTypeIcon from "./EventTypeIcon";
import TestStatusBadge from "./TestStatusBadge";
import type { EventSummary, TestStatus } from "../api/events";

type RequestListItemProps = {
  item: EventSummary;
  selected: boolean;
  onClick: () => void;
};

function formatTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("en-US", { hour12: false });
}

function AppLabel({ app }: { app: string }) {
  if (!app) return null;
  return (
    <Typography
      component="span"
      sx={{
        fontSize: 10,
        fontWeight: 600,
        color: neutral.textSecondary,
        flexShrink: 0,
        ml: 0.5,
      }}
    >
      · {app}
    </Typography>
  );
}

const httpSummaryRe = /^(?:←\s+)?(\w+)\s+(.+?)\s+→\s+(.+)$/;
const numericOutcomeRe = /^\d+$/;

function HttpRow({ item }: { item: EventSummary }) {
  const match = item.summary.match(httpSummaryRe);
  const method = match?.[1] ?? "???";
  const path = match?.[2] ?? item.summary;
  const outcome = match?.[3] ?? "Failed";
  const status = numericOutcomeRe.test(outcome) ? Number.parseInt(outcome, 10) : null;

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
        <Typography
          component="span"
          sx={{
            fontFamily: mono,
            fontSize: 11,
            fontWeight: 700,
            color: neutral.textSecondary,
            flexShrink: 0,
          }}
        >
          {method}
        </Typography>
        <Typography
          component="span"
          sx={{
            fontFamily: mono,
            fontSize: 12,
            fontWeight: 500,
            color: neutral.textPrimary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
          title={item.summary}
        >
          {path}
        </Typography>
      </Stack>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 0.25 }}>
        <Stack direction="row" alignItems="center" sx={{ flex: 1, mr: 1, minWidth: 0 }}>
          <Typography
            component="span"
            sx={{ fontSize: 11, color: neutral.textSecondary, flexShrink: 0 }}
          >
            {formatTime(item.timestamp)}
          </Typography>
          <AppLabel app={item.app} />
        </Stack>
        {status === null ? (
          <Chip
            label={outcome}
            size="small"
            color="error"
            sx={{ fontWeight: 600, fontSize: 12, height: 22 }}
          />
        ) : (
          <StatusBadge status={status} />
        )}
      </Stack>
    </Box>
  );
}

function LogRow({ item }: { item: EventSummary }) {
  const match = item.summary.match(/^(\w+)\s+(.+?):\s+(.*)$/);
  const level = match?.[1] ?? "INFO";
  const logger = match?.[2] ?? "";
  const message = match?.[3] ?? item.summary;

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
        <Typography
          component="span"
          sx={{
            fontFamily: mono,
            fontSize: 11,
            fontWeight: 700,
            color: neutral.textSecondary,
            flexShrink: 0,
          }}
        >
          {level}
        </Typography>
        <Typography
          component="span"
          sx={{
            fontSize: 12,
            fontWeight: 500,
            color: neutral.textPrimary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
          title={item.summary}
        >
          {message}
        </Typography>
      </Stack>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 0.25 }}>
        <Stack direction="row" alignItems="center" sx={{ flex: 1, mr: 1, minWidth: 0 }}>
          <Typography
            component="span"
            sx={{
              fontSize: 11,
              color: neutral.textSecondary,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {logger}
          </Typography>
          <AppLabel app={item.app} />
        </Stack>
        <Typography component="span" sx={{ fontSize: 11, color: neutral.textDisabled, flexShrink: 0 }}>
          {formatTime(item.timestamp)}
        </Typography>
      </Stack>
    </Box>
  );
}

function ExceptionRow({ item }: { item: EventSummary }) {
  const colonIdx = item.summary.indexOf(":");
  const excType = colonIdx > 0 ? item.summary.slice(0, colonIdx) : item.summary;
  const excValue = colonIdx > 0 ? item.summary.slice(colonIdx + 2) : "";

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
        <Typography
          component="span"
          sx={{
            fontFamily: mono,
            fontSize: 12,
            fontWeight: 600,
            color: "#b3261e",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
          title={item.summary}
        >
          {excType}
        </Typography>
      </Stack>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 0.25 }}>
        <Stack direction="row" alignItems="center" sx={{ flex: 1, mr: 1, minWidth: 0 }}>
          <Typography
            component="span"
            sx={{
              fontSize: 11,
              color: neutral.textSecondary,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {excValue}
          </Typography>
          <AppLabel app={item.app} />
        </Stack>
        <Typography component="span" sx={{ fontSize: 11, color: neutral.textDisabled, flexShrink: 0 }}>
          {formatTime(item.timestamp)}
        </Typography>
      </Stack>
    </Box>
  );
}

const testSummaryRe = /^(PASSED|FAILED|ERROR|SKIPPED|XFAILED|XPASSED)\s+(.+)$/;

function testSummary(item: EventSummary): { status: TestStatus; testId: string } {
  const match = item.summary.match(testSummaryRe);
  return {
    status: (match?.[1]?.toLowerCase() ?? "error") as TestStatus,
    testId: match?.[2] ?? item.summary,
  };
}

function splitTestId(testId: string): { context: string; invocation: string } {
  const separatorIndex = testId.lastIndexOf("::");
  if (separatorIndex === -1) {
    return { context: "", invocation: testId };
  }

  return {
    context: testId.slice(0, separatorIndex),
    invocation: testId.slice(separatorIndex + 2),
  };
}

function TestRow({ item }: { item: EventSummary }) {
  const { status, testId } = testSummary(item);
  const { context, invocation } = splitTestId(testId);

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
        <TestStatusBadge status={status} />
        <Typography
          component="span"
          sx={{
            fontFamily: mono,
            fontSize: 12,
            fontWeight: 500,
            color: neutral.textPrimary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
          title={testId}
        >
          {invocation}
        </Typography>
      </Stack>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 0.25 }}>
        <Stack direction="row" alignItems="center" sx={{ flex: 1, mr: 1, minWidth: 0 }}>
          {context && (
            <Typography
              component="span"
              sx={{
                fontFamily: mono,
                fontSize: 11,
                color: neutral.textSecondary,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={context}
            >
              {context}
            </Typography>
          )}
          <AppLabel app={item.app} />
        </Stack>
        <Typography component="span" sx={{ fontSize: 11, color: neutral.textDisabled, flexShrink: 0 }}>
          {formatTime(item.timestamp)}
        </Typography>
      </Stack>
    </Box>
  );
}

function eventLevel(item: EventSummary): string | undefined {
  if (item.event_type !== "log") return undefined;
  const match = item.summary.match(/^(\w+)\s+/);
  return match?.[1];
}

function eventStatus(item: EventSummary): TestStatus | undefined {
  return item.event_type === "test" ? testSummary(item).status : undefined;
}

export default function RequestListItem({ item, selected, onClick }: RequestListItemProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selected && ref.current) {
      ref.current.scrollIntoView({ block: "nearest" });
    }
  }, [selected]);

  return (
    <ListItemButton
      ref={ref}
      selected={selected}
      onClick={onClick}
      sx={{
        py: 1.1,
        px: 1.5,
        alignItems: "flex-start",
        gap: 1,
        borderBottom: `1px solid ${neutral.border}`,
        borderLeft: "2px solid transparent",
        "&:hover": { bgcolor: neutral.hover },
        "&.Mui-selected": {
          bgcolor: "transparent",
          borderLeftColor: neutral.textPrimary,
          "&:hover": { bgcolor: neutral.selectedHover },
        },
      }}
    >
      <Box sx={{ pt: 0.25, flexShrink: 0 }}>
        <EventTypeIcon
          eventType={item.event_type}
          level={eventLevel(item)}
          status={eventStatus(item)}
          size={18}
        />
      </Box>
      {(item.event_type === "http" || item.event_type === "http_incoming") && (
        <HttpRow item={item} />
      )}
      {item.event_type === "log" && <LogRow item={item} />}
      {item.event_type === "exception" && <ExceptionRow item={item} />}
      {item.event_type === "test" && <TestRow item={item} />}
    </ListItemButton>
  );
}
