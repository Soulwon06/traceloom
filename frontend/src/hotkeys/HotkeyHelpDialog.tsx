import { useAtom } from "jotai";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { hotkeyHelpOpenAtom } from "../atoms/hotkeyHelp";
import { neutral, neutralSurface } from "../theme";
import { HOTKEYS } from "./registry";
import type { HotkeyGroup } from "./types";
import Kbd from "../components/Kbd";
import BilingualLabel from "../components/BilingualLabel";

const GROUP_ORDER: HotkeyGroup[] = ["General", "Navigation", "Filters", "Detail", "Actions"];

const groupLabels: Record<HotkeyGroup, string> = {
  General: "通用",
  Navigation: "导航",
  Filters: "筛选",
  Detail: "详情",
  Actions: "操作",
};

const descriptionLabels: Record<string, string> = {
  "Show keyboard shortcuts": "显示键盘快捷键",
  "Focus search": "聚焦搜索",
  "Dismiss / blur / deselect": "关闭 / 失焦 / 取消选择",
  "Next event": "下一个事件",
  "Previous event": "上一个事件",
  "Expand or enter child": "展开或进入子项",
  "Collapse or go to parent": "折叠或返回父项",
  "Clear selection": "清除选择",
  "Clear all filters": "清除全部筛选",
  "Clear all events": "清空全部事件",
  "Toggle query parameters": "展开或收起查询参数",
  "Toggle request headers": "展开或收起请求头",
  "Toggle response headers": "展开或收起响应头",
  "Toggle request body": "展开或收起请求体",
  "Toggle response body": "展开或收起响应体",
  "Copy request body": "复制请求体",
  "Copy response body": "复制响应体",
};

/** Deduplicate entries that share a description within the same group (e.g. j and ArrowDown). */
function deduplicatedEntries(group: HotkeyGroup) {
  const entries = HOTKEYS.filter((h) => h.group === group);
  const seen = new Map<string, { labels: string[]; description: string }>();
  for (const entry of entries) {
    const existing = seen.get(entry.description);
    if (existing) {
      existing.labels.push(entry.label);
    } else {
      seen.set(entry.description, { labels: [entry.label], description: entry.description });
    }
  }
  return [...seen.values()];
}

export default function HotkeyHelpDialog() {
  const [open, setOpen] = useAtom(hotkeyHelpOpenAtom);

  return (
    <Dialog
      open={open}
      onClose={() => setOpen(false)}
      maxWidth="sm"
      fullWidth
      slotProps={{
        paper: {
          sx: { bgcolor: neutralSurface, color: neutral.textPrimary, backgroundImage: "none" },
        },
      }}
    >
      <DialogTitle
        component="div"
        sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pb: 0 }}
      >
        <BilingualLabel title="键盘快捷键" english="Keyboard Shortcuts" />
        <IconButton size="small" onClick={() => setOpen(false)} sx={{ color: neutral.textSecondary }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Stack spacing={2.5}>
          {GROUP_ORDER.map((group) => {
            const rows = deduplicatedEntries(group);
            if (rows.length === 0) return null;
            return (
              <Box key={group}>
                <Typography
                  variant="overline"
                  sx={{
                    color: neutral.textSecondary,
                    fontWeight: 700,
                    letterSpacing: 1.5,
                    mb: 0.5,
                    display: "block",
                  }}
                >
                  {groupLabels[group]} {group}
                </Typography>
                <Stack spacing={0.5}>
                  {rows.map((row) => (
                    <Stack
                      key={row.description}
                      direction="row"
                      alignItems="center"
                      justifyContent="space-between"
                      sx={{ py: 0.5 }}
                    >
                      <BilingualLabel
                        title={descriptionLabels[row.description] ?? row.description}
                        english={row.description}
                      />
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        {row.labels.map((label, i) => (
                          <span key={label}>
                            {i > 0 && (
                              <Typography
                                component="span"
                                variant="caption"
                                sx={{ color: neutral.textDisabled, mx: 0.5 }}
                              >
                                /
                              </Typography>
                            )}
                            <Kbd>{label}</Kbd>
                          </span>
                        ))}
                      </Stack>
                    </Stack>
                  ))}
                </Stack>
              </Box>
            );
          })}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
