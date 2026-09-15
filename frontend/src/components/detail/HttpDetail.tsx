import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import StatusBadge from "../StatusBadge";
import MethodBadge from "../MethodBadge";
import Section from "../Section";
import BilingualLabel from "../BilingualLabel";
import ExplainedField from "./ExplainedField";
import { parseDisplayUrl, parseQueryParams } from "../../utils/url";
import type { EventDetail, HttpEventData } from "../../api/events";

const mono = "'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace";

const statusDescriptions: Record<number, { title: string; english: string }> = {
  200: { title: "请求成功", english: "OK" },
  404: { title: "未找到资源", english: "Not Found" },
  429: { title: "请求受到限制", english: "Too Many Requests" },
  500: { title: "服务器内部错误", english: "Internal Server Error" },
};

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(2)} s`;
}

export default function HttpDetail({ detail }: { detail: EventDetail & { data: HttpEventData } }) {
  const d = detail.data;
  const { host, path } = parseDisplayUrl(d.url);
  const queryParams = parseQueryParams(d.url);
  const statusDescription = d.status_code == null ? undefined : statusDescriptions[d.status_code];

  return (
    <Box sx={{ p: 2, overflowY: "auto" }}>
      <Box sx={{ mb: 2 }}>
        <Box sx={{ minWidth: 0, mb: 1.5 }}>
          <BilingualLabel title="请求" english="Request" />
          <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mt: 0.75, minWidth: 0 }}>
            <MethodBadge method={d.method} size="medium" />
            <Typography
              sx={{ fontFamily: mono, fontSize: 14, fontWeight: 500, wordBreak: "break-all", minWidth: 0 }}
            >
              {path}
            </Typography>
          </Stack>
        </Box>

        <Stack direction="row" useFlexGap spacing={2} sx={{ flexWrap: "wrap", alignItems: "flex-start" }}>
          <ExplainedField
            title="主机"
            english="Host"
            value={host}
            what="表示请求目标所属的主机或服务地址。"
            why="它可以帮助确认请求实际发送到了哪个服务。"
            how="如果请求发送到了错误环境或错误服务，可以检查 Host 与 URL。"
          />
          <ExplainedField
            title="状态码"
            english="Status Code"
            value={
              <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap sx={{ flexWrap: "wrap" }}>
                {d.status_code != null ? (
                  <>
                    <StatusBadge status={d.status_code} />
                    {statusDescription && (
                      <Typography sx={{ fontSize: 12, color: "text.secondary", fontFamily: "inherit" }}>
                        {statusDescription.title} {statusDescription.english}
                      </Typography>
                    )}
                  </>
                ) : (
                  <Chip
                    label={d.error?.type ?? "失败 Failed"}
                    size="small"
                    color="error"
                    sx={{ fontWeight: 600, fontSize: 12, height: 22 }}
                  />
                )}
              </Stack>
            }
            what="HTTP 状态码表示服务器对本次请求的处理结果类别。"
            why="它可以帮助快速判断请求是否成功、发生客户端错误，还是服务器端错误。"
            how="先查看状态码，再结合响应内容、请求参数和相关日志继续排查。"
          />
          <ExplainedField
            title="耗时"
            english="Duration"
            value={formatDuration(d.duration_ms)}
            what="表示一次操作或请求从开始到结束所花费的时间。"
            why="它可以帮助发现明显较慢的请求或步骤。"
            how="可以将异常偏慢的事件与正常事件进行比较，再检查网络、服务调用或内部处理步骤。"
          />
          <Box sx={{ minWidth: 120, flex: "1 1 120px" }}>
            <BilingualLabel title="库" english="Library" />
            <Chip label={d.library} size="small" variant="outlined" sx={{ mt: 0.5, fontSize: 12 }} />
          </Box>
          <Box sx={{ minWidth: 160, flex: "1 1 160px" }}>
            <BilingualLabel title="时间" english="Timestamp" />
            <Typography sx={{ fontSize: 12, color: "text.disabled", mt: 0.5, wordBreak: "break-word" }}>
              {new Date(detail.timestamp).toLocaleString()}
            </Typography>
          </Box>
        </Stack>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {d.error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle sx={{ fontFamily: mono }}>{d.error.type}</AlertTitle>
          <Typography sx={{ fontFamily: mono, fontSize: 12, whiteSpace: "pre-wrap" }}>
            {d.error.message}
          </Typography>
          {d.error.module && (
            <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.5 }}>
              {d.error.module}
            </Typography>
          )}
        </Alert>
      )}

      <Section
        title="Request"
        side="request"
        headers={d.request_headers}
        body={d.request_body ?? null}
        bodySize={d.request_body_size ?? 0}
        queryParams={queryParams}
      />

      <Section
        title="Response"
        side="response"
        headers={d.response_headers ?? {}}
        body={d.response_body ?? null}
        bodySize={d.response_body_size ?? 0}
      />
    </Box>
  );
}
