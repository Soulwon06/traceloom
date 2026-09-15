import type { SxProps, Theme } from "@mui/material";
import { mono } from "../../theme";

export const testDetailStyles: Record<string, SxProps<Theme>> = {
  root: {
    p: 2,
    overflowY: "auto",
  },
  header: {
    mb: 2,
  },
  title: {
    fontFamily: mono,
    fontSize: 16,
    fontWeight: 700,
    wordBreak: "break-word",
  },
  testId: {
    fontFamily: mono,
    mt: 1,
    fontSize: 12,
    color: "text.secondary",
    wordBreak: "break-all",
  },
  metadata: {
    mt: 1.5,
    flexWrap: "wrap",
  },
  sectionTitle: {
    fontWeight: 700,
    mb: 0.75,
  },
  timingPaper: {
    p: 1.5,
    mb: 2,
  },
  timingValue: {
    fontFamily: mono,
    fontSize: 12,
    color: "text.secondary",
  },
  fixtureList: {
    flexWrap: "wrap",
    mb: 2,
  },
  failurePaper: {
    mb: 1.5,
    overflow: "hidden",
    borderColor: "rgba(239,154,154,0.35)",
  },
  failureHeader: {
    px: 1.5,
    py: 1,
    bgcolor: "rgba(239,154,154,0.06)",
  },
  failureMessage: {
    px: 1.5,
    pt: 1.25,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  traceback: {
    fontFamily: mono,
    m: 0,
    p: 1.5,
    fontSize: 12,
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    bgcolor: "rgba(0,0,0,0.025)",
    overflow: "auto",
  },
};
