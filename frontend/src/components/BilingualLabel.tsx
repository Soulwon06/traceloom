import Box from "@mui/material/Box";

type BilingualLabelProps = {
  title: string;
  english: string;
  compact?: boolean;
};

/** Shared visual rule: Chinese is the quick-reading layer, English the term layer. */
export default function BilingualLabel({ title, english, compact = false }: BilingualLabelProps) {
  if (compact) {
    return (
      <Box component="span" sx={{ whiteSpace: "nowrap" }}>
        <Box component="span" sx={{ fontWeight: 600 }}>
          {title}
        </Box>{" "}
        <Box component="span" sx={{ color: "text.secondary", fontSize: "0.92em" }}>
          {english}
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.25 }}>{title}</Box>
      <Box sx={{ fontSize: 11, color: "text.secondary", lineHeight: 1.25, mt: 0.2 }}>
        {english}
      </Box>
    </Box>
  );
}
