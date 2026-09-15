import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import LogLevelBadge from "../LogLevelBadge";
import BodyViewer from "../BodyViewer";
import BilingualLabel from "../BilingualLabel";
import type { EventDetail, LogEventData } from "../../api/events";

const mono = "'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace";

const levelLabels: Record<string, string> = {
  ERROR: "错误",
  WARNING: "警告",
  INFO: "信息",
  DEBUG: "调试",
};

export default function LogDetail({ detail }: { detail: EventDetail & { data: LogEventData } }) {
  const d = detail.data;
  const hasExtra = d.extra && Object.keys(d.extra).length > 0;
  const levelTitle = levelLabels[d.level] ?? d.level;

  return (
    <Box sx={{ p: 2, overflowY: "auto" }}>
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <BilingualLabel title="日志" english="Log" />
          <LogLevelBadge level={d.level} />
          <BilingualLabel title={levelTitle} english={d.level} compact />
          <Typography sx={{ fontFamily: mono, fontSize: 14, fontWeight: 600 }}>
            {d.logger_name}
          </Typography>
        </Stack>

        <Typography
          sx={{
            fontSize: 14,
            mb: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {d.message}
        </Typography>

        <Stack direction="row" useFlexGap spacing={2} sx={{ flexWrap: "wrap", alignItems: "flex-start" }}>
          {d.pathname && d.lineno && (
            <Box sx={{ minWidth: 180, flex: "1 1 180px" }}>
              <BilingualLabel title="来源" english="Source" />
              <Chip
                label={`${d.pathname}:${d.lineno}`}
                size="small"
                variant="outlined"
                sx={{ mt: 0.5, fontFamily: mono, fontSize: 11, height: 22, color: "text.secondary", borderColor: "divider" }}
              />
            </Box>
          )}
          {d.func_name && (
            <Box sx={{ minWidth: 140, flex: "1 1 140px" }}>
              <BilingualLabel title="函数" english="Function" />
              <Chip
                label={d.func_name}
                size="small"
                variant="outlined"
                sx={{ mt: 0.5, fontFamily: mono, fontSize: 11, height: 22, color: "text.secondary", borderColor: "divider" }}
              />
            </Box>
          )}
          <Box sx={{ minWidth: 160, flex: "1 1 160px" }}>
            <BilingualLabel title="时间" english="Timestamp" />
            <Typography variant="body2" color="text.disabled" sx={{ fontSize: 12, mt: 0.5 }}>
              {new Date(detail.timestamp).toLocaleString()}
            </Typography>
          </Box>
        </Stack>
      </Box>

      {d.exc_text && (
        <>
          <Divider sx={{ mb: 2 }} />
          <BilingualLabel title="异常" english="Exception" />
          <Paper
            variant="outlined"
            sx={{
              p: 1.5,
              mb: 2,
              bgcolor: "rgba(239,154,154,0.04)",
              borderColor: "rgba(239,154,154,0.2)",
            }}
          >
            <Typography
              component="pre"
              sx={{
                fontFamily: mono,
                fontSize: 12,
                m: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "#ef9a9a",
              }}
            >
              {d.exc_text}
            </Typography>
          </Paper>
        </>
      )}

      {hasExtra && (
        <>
          <Divider sx={{ mb: 2 }} />
          <BilingualLabel title="附加数据" english="Extra" />
          <Paper variant="outlined" sx={{ p: 1 }}>
            <BodyViewer data={JSON.stringify(d.extra, null, 2)} />
          </Paper>
        </>
      )}
    </Box>
  );
}
