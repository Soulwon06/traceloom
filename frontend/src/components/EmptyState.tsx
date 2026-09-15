import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import BrandMark from "./BrandMark";

export default function EmptyState() {
  return (
    <Stack alignItems="center" justifyContent="center" sx={{ height: "100%", p: 4 }}>
      <Stack alignItems="center" sx={{ maxWidth: { xs: 480, lg: 640 }, width: "100%" }}>
        <Box sx={{ mb: { xs: 3, lg: 4 } }}>
          <BrandMark showTagline />
        </Box>
        <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.5, fontSize: { lg: "1.6rem" } }}>
          还没有捕获到运行事件
        </Typography>
        <Typography
          variant="body1"
          color="text.secondary"
          sx={{ mb: { xs: 4, lg: 5 }, fontSize: { lg: "1.05rem" } }}
        >
          启动你的应用并触发请求后，TraceLoom 会在这里显示运行记录。
        </Typography>

      </Stack>
    </Stack>
  );
}
