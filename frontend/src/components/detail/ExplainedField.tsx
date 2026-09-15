import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import TermExplanation from "../TermExplanation";
import { mono } from "../../theme";

type ExplainedFieldProps = {
  title: string;
  english: string;
  value: ReactNode;
  what: string;
  why: string;
  how: string;
};

export default function ExplainedField({
  title,
  english,
  value,
  what,
  why,
  how,
}: ExplainedFieldProps) {
  return (
    <Box sx={{ minWidth: 0, flex: "1 1 150px" }}>
      <TermExplanation title={title} english={english} what={what} why={why} how={how} />
      <Box sx={{ fontFamily: mono, fontSize: 13, color: "text.primary", mt: 0.5, wordBreak: "break-word" }}>
        {value}
      </Box>
    </Box>
  );
}
