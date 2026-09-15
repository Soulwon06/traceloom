import { useAtom } from "jotai";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import Collapse from "@mui/material/Collapse";
import ButtonBase from "@mui/material/ButtonBase";
import ExpandMore from "@mui/icons-material/ExpandMore";
import CallMade from "@mui/icons-material/CallMade";
import CallReceived from "@mui/icons-material/CallReceived";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import HeadersTable from "./HeadersTable";
import BodyViewer from "./BodyViewer";
import CopyButton from "./CopyButton";
import BilingualLabel from "./BilingualLabel";
import TermExplanation from "./TermExplanation";
import {
  headersOpenAtom,
  bodyOpenAtom,
  queryParamsOpenAtom,
  type Side,
} from "../atoms/sectionState";

type SectionProps = {
  title: string;
  side: Side;
  headers: Record<string, string>;
  body: string | null;
  bodySize: number;
  queryParams?: [string, string][];
};

const chevronSx = (open: boolean) => ({
  color: "text.secondary",
  transform: open ? "rotate(180deg)" : "rotate(0deg)",
  transition: "transform 150ms",
});

export default function Section({
  title,
  side,
  headers,
  body,
  bodySize,
  queryParams,
}: SectionProps) {
  const [queryParamsOpen, setQueryParamsOpen] = useAtom(queryParamsOpenAtom[side]);
  const [headersOpen, setHeadersOpen] = useAtom(headersOpenAtom[side]);
  const [bodyOpen, setBodyOpen] = useAtom(bodyOpenAtom[side]);
  const headerCount = Object.keys(headers).length;
  const hasQueryParams = queryParams && queryParams.length > 0;
  const isRequest = side === "request";
  const Icon = isRequest ? CallMade : CallReceived;
  const headersTitle = isRequest ? "请求头" : "响应头";
  const headersExplanation = isRequest
    ? {
        what: "请求发送时附带的 HTTP 元数据，例如内容类型、认证信息和客户端信息。",
        why: "它可以帮助确认客户端实际发送了哪些协议级信息。",
        how: "如果服务端行为与预期不一致，可以检查 Content-Type、Authorization、Accept 等相关 Header。",
      }
    : {
        what: "服务器返回的 HTTP 元数据，例如内容类型、缓存和服务端信息。",
        why: "它可以帮助确认服务端实际返回了哪些协议级信息。",
        how: "如果客户端解析或行为与预期不一致，可以检查 Content-Type、缓存和相关 Header。",
      };
  const bodyTitle = isRequest ? "请求体" : "响应体";
  const bodyExplanation = isRequest
    ? {
        what: "请求发送给服务器的主体数据。",
        why: "它可以帮助确认实际发送的参数、Prompt 或结构化内容是否符合预期。",
        how: "当服务返回异常结果时，可以对照接口要求检查请求体的字段和值。",
      }
    : {
        what: "服务器返回的主体内容。",
        why: "它通常包含实际业务结果、错误信息或模型输出。",
        how: "可以结合状态码和请求内容检查服务实际返回了什么。",
      };

  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
        <Icon
          sx={{
            fontSize: 16,
            color: isRequest ? "primary.main" : "success.main",
          }}
        />
        <BilingualLabel title={isRequest ? "请求" : "响应"} english={title} />
      </Stack>
      {hasQueryParams && (
        <Paper variant="outlined" sx={{ mb: 1 }}>
          <ButtonBase
            disableRipple
            onClick={() => setQueryParamsOpen((o) => !o)}
            sx={{
              width: "100%",
              justifyContent: "space-between",
              p: 1,
              textAlign: "left",
            }}
          >
            <BilingualLabel title="查询参数" english={`Query Parameters (${queryParams.length})`} />
            <ExpandMore fontSize="small" sx={chevronSx(queryParamsOpen)} />
          </ButtonBase>
          <Collapse in={queryParamsOpen}>
            <Box sx={{ px: 1, pb: 1 }}>
              <Table size="small">
                <TableBody>
                  {queryParams.map(([key, value], i) => (
                    <TableRow key={`${key}-${i}`}>
                      <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap", width: "1%" }}>
                        {key}
                      </TableCell>
                      <TableCell sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                        {value}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </Paper>
      )}
      <Paper variant="outlined" sx={{ mb: 1 }}>
        <Stack direction="row" alignItems="center" sx={{ px: 1, minWidth: 0 }}>
          <ButtonBase
            disableRipple
            onClick={() => setHeadersOpen((o) => !o)}
            sx={{
              flex: 1,
              minWidth: 0,
              justifyContent: "space-between",
              py: 1,
              textAlign: "left",
            }}
          >
            <BilingualLabel title={headersTitle} english={`Headers (${headerCount})`} />
            <ExpandMore fontSize="small" sx={chevronSx(headersOpen)} />
          </ButtonBase>
          <TermExplanation
            title={headersTitle}
            english={isRequest ? "Request Headers" : "Response Headers"}
            {...headersExplanation}
          />
        </Stack>
        <Collapse in={headersOpen}>
          <Box sx={{ px: 1, pb: 1 }}>
            <HeadersTable headers={headers} />
          </Box>
        </Collapse>
      </Paper>
      {body && (
        <Paper variant="outlined">
          <Stack direction="row" alignItems="center" sx={{ p: 1 }}>
            <ButtonBase
              disableRipple
              onClick={() => setBodyOpen((o) => !o)}
              sx={{ flex: 1, justifyContent: "space-between", textAlign: "left" }}
            >
              <BilingualLabel title={bodyTitle} english={`Body (${bodySize} bytes)`} />
              <ExpandMore fontSize="small" sx={chevronSx(bodyOpen)} />
            </ButtonBase>
            <TermExplanation
              title={bodyTitle}
              english={isRequest ? "Request Body" : "Response Body"}
              {...bodyExplanation}
            />
            <CopyButton text={body} hotkeyLabel={isRequest ? "c" : "C"} />
          </Stack>
          <Collapse in={bodyOpen}>
            <Box sx={{ px: 1, pb: 1 }}>
              <BodyViewer data={body} />
            </Box>
          </Collapse>
        </Paper>
      )}
    </Box>
  );
}
