import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { EventDetail, TestEventData } from "../../api/events";
import { mono } from "../../theme";
import CopyButton from "../CopyButton";
import TestStatusBadge from "../TestStatusBadge";
import BilingualLabel from "../BilingualLabel";
import { testDetailStyles as styles } from "./TestDetail.styles";

function formatDuration(durationMs: number): string {
  if (durationMs < 1) return `${durationMs.toFixed(3)} ms`;
  if (durationMs < 1000) return `${durationMs.toFixed(1)} ms`;
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function vscodeUrl(path: string, line: number | null | undefined): string {
  return line == null
    ? `vscode://file/${encodeURI(path)}`
    : `vscode://file/${encodeURI(path)}:${line}`;
}

export default function TestDetail({ detail }: { detail: EventDetail & { data: TestEventData } }) {
  const data = detail.data;
  const timings = [
    { title: "总计", english: "Total", duration: data.duration_ms },
    { title: "准备", english: "Setup", duration: data.setup_duration_ms },
    { title: "执行", english: "Call", duration: data.call_duration_ms },
    { title: "清理", english: "Teardown", duration: data.teardown_duration_ms },
  ];

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <TestStatusBadge status={data.status} />
          <Typography sx={styles.title}>{data.name}</Typography>
          <Chip label={data.framework} size="small" variant="outlined" />
        </Stack>

        <Typography sx={styles.testId}>{data.test_id}</Typography>

        <Stack direction="row" alignItems="center" spacing={1} sx={styles.metadata}>
          <Chip
            component={Link}
            clickable
            href={vscodeUrl(data.path, data.line)}
            label={`${data.path}${data.line == null ? "" : `:${data.line}`}`}
            size="small"
            variant="outlined"
            sx={{ fontFamily: mono }}
          />
          <Chip
            label={`运行 Run ${data.run_id}`}
            size="small"
            variant="outlined"
            sx={{ fontFamily: mono }}
          />
          {data.worker_id !== "master" ? (
            <Chip
              label={data.worker_id}
              size="small"
              variant="outlined"
              sx={{ fontFamily: mono }}
            />
          ) : null}
          <Typography variant="body2" color="text.disabled" sx={{ fontSize: 12 }}>
            {new Date(detail.timestamp).toLocaleString()}
          </Typography>
        </Stack>
      </Box>

      <Divider sx={{ mb: 2 }} />

      <Typography variant="subtitle2" sx={styles.sectionTitle}>
        <BilingualLabel title="耗时" english="Timing" />
      </Typography>
      <Paper variant="outlined" sx={styles.timingPaper}>
        <Stack direction="row" spacing={3} useFlexGap sx={{ flexWrap: "wrap" }}>
          {timings.map(({ title, english, duration }) => (
            <Box key={english}>
              <BilingualLabel title={title} english={english} />
              <Typography sx={styles.timingValue}>{formatDuration(duration)}</Typography>
            </Box>
          ))}
        </Stack>
      </Paper>

      <Typography variant="subtitle2" sx={styles.sectionTitle}>
        <BilingualLabel title="夹具" english="Fixtures" />
      </Typography>
      <Stack direction="row" spacing={0.75} useFlexGap sx={styles.fixtureList}>
        {data.fixtures.length > 0 ? (
          data.fixtures.map((fixture) => (
            <Chip
              key={fixture}
              label={fixture}
              size="small"
              variant="outlined"
              sx={{ fontFamily: mono }}
            />
          ))
        ) : (
          <Typography variant="body2" color="text.secondary">
            无夹具 No fixtures
          </Typography>
        )}
      </Stack>

      {data.failures.length > 0 ? (
        <>
          <Typography variant="subtitle2" sx={styles.sectionTitle}>
            <BilingualLabel title="失败" english="Failures" />
          </Typography>
          {data.failures.map((failure, index) => (
            <Paper key={`${failure.phase}-${index}`} variant="outlined" sx={styles.failurePaper}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={styles.failureHeader}
              >
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Chip
                    label={failure.phase.toUpperCase()}
                    size="small"
                    color="error"
                    variant="outlined"
                    sx={{ fontFamily: mono }}
                  />
                  {failure.exception_type ? (
                    <Typography sx={{ fontFamily: mono, fontSize: 13, fontWeight: 700 }}>
                      {failure.exception_type}
                    </Typography>
                  ) : null}
                </Stack>
                <CopyButton text={failure.traceback_text} />
              </Stack>
              {failure.message ? (
                <Typography sx={styles.failureMessage}>{failure.message}</Typography>
              ) : null}
              <Typography component="pre" sx={styles.traceback}>
                {failure.traceback_text}
              </Typography>
            </Paper>
          ))}
        </>
      ) : null}
    </Box>
  );
}
