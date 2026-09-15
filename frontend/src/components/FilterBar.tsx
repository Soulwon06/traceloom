import { useAtom } from "jotai";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputAdornment from "@mui/material/InputAdornment";
import SearchIcon from "@mui/icons-material/Search";
import { neutral } from "../theme";
import {
  hostFilterAtom,
  methodFilterAtom,
  searchFilterAtom,
  eventTypeFilterAtom,
  appFilterAtom,
  sessionFilterAtom,
} from "../atoms/filters";
import { useGetMeta } from "../api/events";
import EventTypeIcon from "./EventTypeIcon";
import BilingualLabel from "./BilingualLabel";
import type { EventType } from "../api/events";
import { groupingModeAtom } from "../atoms/grouping";
import { useFilteredRequests } from "../hooks/useFilteredRequests";
import { availableGroupingOptions, type GroupingMode } from "../hierarchy/definitions";

export default function FilterBar() {
  const [host, setHost] = useAtom(hostFilterAtom);
  const [method, setMethod] = useAtom(methodFilterAtom);
  const [search, setSearch] = useAtom(searchFilterAtom);
  const [eventType, setEventType] = useAtom(eventTypeFilterAtom);
  const [app, setApp] = useAtom(appFilterAtom);
  const [session, setSession] = useAtom(sessionFilterAtom);
  const [groupingMode, setGroupingMode] = useAtom(groupingModeAtom);

  const { data: meta } = useGetMeta({ refetchInterval: 10_000 });
  const { data: loadedEvents = [] } = useFilteredRequests();
  const groupingOptions = availableGroupingOptions(loadedEvents);
  const effectiveGroupingMode = groupingOptions.some((option) => option.value === groupingMode)
    ? groupingMode
    : "none";

  const neutralSelect = {
    color: neutral.textPrimary,
    ".MuiOutlinedInput-notchedOutline": { borderColor: neutral.border },
    "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: neutral.textDisabled },
    ".MuiSvgIcon-root": { color: neutral.textMuted },
  };

  const eventTypeLabels: Record<string, string> = {
    http: "HTTP（出站）",
    http_incoming: "HTTP（入站）",
    log: "日志",
    exception: "异常",
    test: "测试",
  };
  const groupLabels: Record<string, string> = {
    none: "无分组",
    "pytest:test_directory": "测试目录",
    "pytest:test_file": "测试文件",
    "pytest:test_class": "测试类",
    "pytest:test_case": "测试用例",
    "http_request:hostname": "远程主机",
  };

  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 1 }}>
      <Select
        size="small"
        value={effectiveGroupingMode}
        onChange={(e) => setGroupingMode(e.target.value as GroupingMode)}
        sx={{ minWidth: 145, ...neutralSelect }}
        renderValue={(value) => {
          const option = groupingOptions.find((candidate) => candidate.value === value);
          return <BilingualLabel compact title="分组" english={groupLabels[option?.value ?? "none"] ?? option?.label ?? "None"} />;
        }}
      >
        {groupingOptions.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            <BilingualLabel compact title="分组" english={groupLabels[option.value] ?? option.label} />
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        displayEmpty
        value={eventType}
        onChange={(e) => setEventType(e.target.value)}
        sx={{ minWidth: 130, ...neutralSelect }}
        renderValue={(v) => {
          if (!v) return <BilingualLabel compact title="全部类型" english="All Types" />;
          return (
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <EventTypeIcon eventType={v as EventType} size={16} />
              <BilingualLabel compact title={eventTypeLabels[v] ?? v} english={v} />
            </Stack>
          );
        }}
      >
        <MenuItem value=""><BilingualLabel compact title="全部类型" english="All Types" /></MenuItem>
        {meta?.event_types.map((t) => (
          <MenuItem key={t} value={t}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <EventTypeIcon eventType={t} size={18} />
              <BilingualLabel compact title={eventTypeLabels[t] ?? t} english={t} />
            </Stack>
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        displayEmpty
        value={method}
        onChange={(e) => setMethod(e.target.value)}
        sx={{ minWidth: 90, ...neutralSelect }}
        renderValue={(v) => v || <BilingualLabel compact title="方法" english="Method" />}
      >
        <MenuItem value=""><BilingualLabel compact title="全部方法" english="All Methods" /></MenuItem>
        {meta?.methods.map((m) => (
          <MenuItem key={m} value={m}>
            {m}
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        displayEmpty
        value={host}
        onChange={(e) => setHost(e.target.value)}
        sx={{ minWidth: 140, ...neutralSelect }}
        renderValue={(v) => v || <BilingualLabel compact title="主机" english="Host" />}
      >
        <MenuItem value=""><BilingualLabel compact title="全部主机" english="All Hosts" /></MenuItem>
        {meta?.hosts.map((h) => (
          <MenuItem key={h} value={h}>
            {h}
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        displayEmpty
        value={app ?? "__all__"}
        onChange={(e) => {
          const v = e.target.value;
          setApp(v === "__all__" ? undefined : v);
        }}
        sx={{ minWidth: 100, ...neutralSelect }}
        renderValue={(v) => {
          if (v === "__all__") return <BilingualLabel compact title="应用" english="App" />;
          if (v === "") return <BilingualLabel compact title="无应用" english="No App" />;
          return v;
        }}
      >
        <MenuItem value="__all__"><BilingualLabel compact title="全部应用" english="All Apps" /></MenuItem>
        {meta?.apps?.includes("") && <MenuItem value=""><BilingualLabel compact title="无应用" english="No App" /></MenuItem>}
        {meta?.apps
          ?.filter((a) => a !== "")
          .map((a) => (
            <MenuItem key={a} value={a}>
              {a}
            </MenuItem>
          ))}
      </Select>
      <Select
        size="small"
        displayEmpty
        value={session ?? "__all__"}
        onChange={(e) => {
          const v = e.target.value;
          setSession(v === "__all__" ? undefined : v);
        }}
        sx={{ minWidth: 110, ...neutralSelect }}
        renderValue={(v) => {
          if (v === "__all__") return <BilingualLabel compact title="会话" english="Session" />;
          if (v === "") return <BilingualLabel compact title="无会话" english="No Session" />;
          return v.length > 12 ? v.slice(0, 8) + "…" : v;
        }}
        title={session ?? ""}
      >
        <MenuItem value="__all__"><BilingualLabel compact title="全部会话" english="All Sessions" /></MenuItem>
        {meta?.sessions?.includes("") && <MenuItem value=""><BilingualLabel compact title="无会话" english="No Session" /></MenuItem>}
        {meta?.sessions
          ?.filter((s) => s !== "")
          .map((s) => (
            <MenuItem key={s} value={s} title={s}>
              {s.length > 24 ? s.slice(0, 20) + "…" : s}
            </MenuItem>
          ))}
      </Select>
      <TextField
        size="small"
        placeholder="搜索 Prompt、回复、模型、URL、错误…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: neutral.textMuted }} />
              </InputAdornment>
            ),
          },
          htmlInput: {
            "data-hotkey-target": "search",
          },
        }}
        sx={{
          minWidth: 200,
          flex: 1,
          "& .MuiOutlinedInput-root": {
            color: neutral.textPrimary,
            "& .MuiOutlinedInput-notchedOutline": { borderColor: neutral.border },
            "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: neutral.textDisabled },
          },
          "& .MuiInputBase-input::placeholder": { color: neutral.textDisabled, opacity: 1 },
        }}
      />
    </Stack>
  );
}
