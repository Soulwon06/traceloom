import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

type BrandMarkProps = {
  inverse?: boolean;
  showTagline?: boolean;
  symbolOnly?: boolean;
};

/** A small, original line mark for the TraceLoom wordmark. */
export default function BrandMark({
  inverse = false,
  showTagline = false,
  symbolOnly = false,
}: BrandMarkProps) {
  const color = inverse ? "#ffffff" : "#202124";
  const secondaryColor = inverse ? "rgba(255,255,255,0.62)" : "text.secondary";

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Box
        component="svg"
        viewBox="0 0 32 32"
        aria-hidden="true"
        sx={{ width: symbolOnly ? 30 : 28, height: symbolOnly ? 30 : 28 }}
      >
        <path
          d="M7 7h18v6H13v12H7V7Zm6 6h12v6H13"
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="square"
          strokeLinejoin="miter"
        />
        <path d="M19 13v12" fill="none" stroke={color} strokeWidth="2" />
      </Box>
      {!symbolOnly && <Box>
        <Typography
          sx={{
            color,
            fontSize: 15,
            lineHeight: 1.1,
            fontWeight: 650,
            letterSpacing: "-0.02em",
          }}
        >
          TraceLoom
        </Typography>
        {showTagline && (
          <Typography
            sx={{
              color: secondaryColor,
              fontSize: 10,
              mt: 0.3,
              lineHeight: 1.2,
              display: { xs: "none", md: "block" },
            }}
          >
            Readable observability for AI applications.
          </Typography>
        )}
      </Box>}
    </Stack>
  );
}
