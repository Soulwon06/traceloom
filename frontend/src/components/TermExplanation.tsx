import { useState } from "react";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import HelpOutline from "@mui/icons-material/HelpOutline";

type TermExplanationProps = {
  title: string;
  english: string;
  what: string;
  why: string;
  how: string;
};

export default function TermExplanation({ title, english, what, why, how }: TermExplanationProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const open = Boolean(anchorEl);

  const handleOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Box>
          <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{title}</Typography>

          <Typography sx={{ fontSize: 11, color: "text.secondary" }}>{english}</Typography>
        </Box>

        <IconButton
          size="small"
          onClick={handleOpen}
          aria-label={`Explain ${english}`}
          sx={{
            p: 0.25,
            color: "text.secondary",
            "&:hover": { color: "text.primary", bgcolor: "action.hover" },
          }}
        >
          <HelpOutline sx={{ fontSize: 16 }} />
        </IconButton>
      </Box>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: "bottom",
          horizontal: "right",
        }}
        transformOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
      >
        <Box sx={{ p: 2, width: { xs: 280, sm: 320 }, boxShadow: 2 }}>
          <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{title}</Typography>

          <Typography
            sx={{
              fontSize: 12,
              color: "text.secondary",
              mb: 1.5,
            }}
          >
            {english}
          </Typography>

          <Typography sx={{ fontSize: 12, fontWeight: 700 }}>是什么？</Typography>
          <Typography sx={{ fontSize: 12, mb: 1.25 }}>{what}</Typography>

          <Typography sx={{ fontSize: 12, fontWeight: 700 }}>为什么看？</Typography>
          <Typography sx={{ fontSize: 12, mb: 1.25 }}>{why}</Typography>

          <Typography sx={{ fontSize: 12, fontWeight: 700 }}>怎么用？</Typography>
          <Typography sx={{ fontSize: 12 }}>{how}</Typography>
        </Box>
      </Popover>
    </Box>
  );
}
