import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import CallReceivedIcon from "@mui/icons-material/CallReceived";
import SubjectIcon from "@mui/icons-material/Subject";
import BugReportIcon from "@mui/icons-material/BugReport";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import type { EventType } from "../api/events";

const Icons: Record<EventType, typeof SwapHorizIcon> = {
  http: SwapHorizIcon,
  http_incoming: CallReceivedIcon,
  log: SubjectIcon,
  exception: BugReportIcon,
  test: FactCheckIcon,
};

const baseColorsDark: Record<EventType, string> = {
  http: "#64b5f6",
  http_incoming: "#81c784",
  log: "#90a4ae",
  exception: "#ef9a9a",
  test: "#81c784",
};

const baseColorsLight: Record<EventType, string> = {
  http: "#1565c0",
  http_incoming: "#2e7d32",
  log: "#546e7a",
  exception: "#c62828",
  test: "#2e7d32",
};

const logLevelColorsDark: Record<string, string> = {
  DEBUG: "#90a4ae",
  INFO: "#90a4ae",
  WARNING: "#ffb74d",
  ERROR: "#ef9a9a",
  CRITICAL: "#ff8a80",
};

const logLevelColorsLight: Record<string, string> = {
  DEBUG: "#546e7a",
  INFO: "#546e7a",
  WARNING: "#e65100",
  ERROR: "#c62828",
  CRITICAL: "#b71c1c",
};

const testStatusColorsDark: Record<string, string> = {
  passed: "#81c784",
  failed: "#ef9a9a",
  error: "#ff8a80",
  skipped: "#90a4ae",
  xfailed: "#ffb74d",
  xpassed: "#64b5f6",
};

const testStatusColorsLight: Record<string, string> = {
  passed: "#2e7d32",
  failed: "#c62828",
  error: "#b71c1c",
  skipped: "#546e7a",
  xfailed: "#e65100",
  xpassed: "#1565c0",
};

type Props = {
  eventType: EventType;
  dark?: boolean;
  level?: string;
  status?: string;
  size?: number;
};

export default function EventTypeIcon({
  eventType,
  dark = false,
  level,
  status,
  size = 18,
}: Props) {
  const Icon = Icons[eventType];
  let color: string;
  if (eventType === "log" && level) {
    const palette = dark ? logLevelColorsDark : logLevelColorsLight;
    color = palette[level] ?? (dark ? baseColorsDark.log : baseColorsLight.log);
  } else if (eventType === "test" && status) {
    const palette = dark ? testStatusColorsDark : testStatusColorsLight;
    color = palette[status] ?? (dark ? baseColorsDark.test : baseColorsLight.test);
  } else {
    color = (dark ? baseColorsDark : baseColorsLight)[eventType];
  }
  return (
    <Icon
      sx={{
        color,
        fontSize: size,
        flexShrink: 0,
      }}
    />
  );
}
