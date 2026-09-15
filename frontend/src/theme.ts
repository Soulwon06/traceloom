import { createTheme } from "@mui/material/styles";

/** Monospace font stack used for URLs, method badges, durations, and table cells. */
export const mono = "'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace";

/** Dark surface color for the toolbar and sidebar. */
export const darkSurface = "#2A2A2E";

/** Reusable white-alpha tokens for elements on dark surfaces. */
export const dark = {
  border: "rgba(255,255,255,0.08)",
  divider: "rgba(255,255,255,0.12)",
  hover: "rgba(255,255,255,0.06)",
  selected: "rgba(255,255,255,0.10)",
  selectedHover: "rgba(255,255,255,0.14)",
  textPrimary: "#fff",
  textSecondary: "rgba(255,255,255,0.6)",
  textDisabled: "rgba(255,255,255,0.4)",
  textMuted: "rgba(255,255,255,0.5)",
} as const;

/** Neutral surface tokens for the readable feed and primary navigation chrome. */
export const neutralSurface = "#fafaf8";
export const neutral = {
  border: "#e7e7e2",
  hover: "rgba(32,33,36,0.045)",
  selected: "rgba(32,33,36,0.07)",
  selectedHover: "rgba(32,33,36,0.10)",
  textPrimary: "#202124",
  textSecondary: "#686b70",
  textDisabled: "#96999e",
  textMuted: "#7b7e84",
} as const;

const theme = createTheme({
  typography: {
    fontSize: 13,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    MuiTableCell: {
      styleOverrides: {
        root: {
          padding: "4px 8px",
          fontSize: 13,
          fontFamily: mono,
        },
      },
    },
  },
});

export default theme;
