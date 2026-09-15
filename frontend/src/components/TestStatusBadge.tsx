import Chip from "@mui/material/Chip";
import type { TestStatus } from "../api/events";
import { mono } from "../theme";

const colors: Record<TestStatus, { color: string; background: string }> = {
  passed: { color: "#2e7d32", background: "#e8f5e9" },
  failed: { color: "#c62828", background: "#ffebee" },
  error: { color: "#b71c1c", background: "#ffebee" },
  skipped: { color: "#546e7a", background: "#eceff1" },
  xfailed: { color: "#e65100", background: "#fff3e0" },
  xpassed: { color: "#1565c0", background: "#e3f2fd" },
};

const darkColors: Record<TestStatus, { color: string; background: string }> = {
  passed: { color: "#81c784", background: "rgba(129,199,132,0.12)" },
  failed: { color: "#ef9a9a", background: "rgba(239,154,154,0.15)" },
  error: { color: "#ff8a80", background: "rgba(255,138,128,0.15)" },
  skipped: { color: "#b0bec5", background: "rgba(176,190,197,0.12)" },
  xfailed: { color: "#ffb74d", background: "rgba(255,183,77,0.12)" },
  xpassed: { color: "#64b5f6", background: "rgba(100,181,246,0.12)" },
};

type Props = {
  status: TestStatus;
  dark?: boolean;
};

export default function TestStatusBadge({ status, dark = false }: Props) {
  const palette = dark ? darkColors : colors;
  const { color, background } = palette[status];

  return (
    <Chip
      label={status.toUpperCase()}
      size="small"
      sx={{
        fontFamily: mono,
        fontWeight: 700,
        fontSize: 10,
        height: 20,
        color,
        bgcolor: background,
        borderRadius: 1,
      }}
    />
  );
}
