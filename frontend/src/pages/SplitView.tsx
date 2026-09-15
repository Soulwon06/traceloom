import { useCallback } from "react";
import { useAtomValue, useSetAtom } from "jotai";
import { useHotkeys } from "react-hotkeys-hook";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import DeleteIcon from "@mui/icons-material/Delete";
import EventNoteOutlinedIcon from "@mui/icons-material/EventNoteOutlined";
import Tooltip from "@mui/material/Tooltip";
import { styled } from "@mui/material/styles";
import { Group, Panel, Separator, type Layout } from "react-resizable-panels";
import { neutralSurface, neutral } from "../theme";
import { useListNavigation } from "../hotkeys/useListNavigation";
import { useGlobalHotkeys } from "../hotkeys/useGlobalHotkeys";
import { useDetailHotkeys } from "../hotkeys/useDetailHotkeys";
import { hotkeyHelpOpenAtom } from "../atoms/hotkeyHelp";
import { snackbarMessageAtom } from "../atoms/snackbar";
import Kbd from "../components/Kbd";
import FilterBar from "../components/FilterBar";
import RequestList from "../components/RequestList";
import RequestDetail from "../components/RequestDetail";
import EmptyState from "../components/EmptyState";
import BrandMark from "../components/BrandMark";
import { useSelectedRequestId } from "../hooks/useSelectedRequestId";
import { sessionFilterAtom } from "../atoms/filters";
import { useEventStore, useClearEvents } from "../api/events";

const ResizeHandle = styled(Separator)(({ theme }) => ({
  padding: "0 1px",
  background: theme.palette.divider,
  outline: "none",
}));

const LAYOUT_KEY = "react-resizable-panels:traceloom-split-view";

function readSavedLayout(): Layout | undefined {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    return raw ? JSON.parse(raw) : undefined;
  } catch {
    return undefined;
  }
}

// Read once at module level so the very first render has the correct layout.
const initialLayout = readSavedLayout();

function SplitViewSkeleton() {
  return (
    <Stack sx={{ height: "100%" }}>
      <Box
        sx={{
          height: 49,
          bgcolor: neutralSurface,
          borderBottom: `1px solid ${neutral.border}`,
        }}
      />
      <Stack direction="row" sx={{ flex: 1, overflow: "hidden" }}>
        <Box sx={{ width: initialLayout?.list ?? "15%", bgcolor: neutralSurface, p: 1 }}>
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton
              key={i}
              variant="rounded"
              height={40}
              sx={{ mb: 0.5, bgcolor: "rgba(32,33,36,0.06)" }}
            />
          ))}
        </Box>
        <Box sx={{ flex: 1 }} />
      </Stack>
    </Stack>
  );
}

export default function SplitView() {
  const [selectedId] = useSelectedRequestId();
  const setHelpOpen = useSetAtom(hotkeyHelpOpenAtom);
  useListNavigation();
  useGlobalHotkeys();
  useDetailHotkeys();

  const onLayoutChanged = useCallback((layout: Layout) => {
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
    } catch {
      // localStorage may be full or unavailable; layout still works, just won't persist.
    }
  }, []);

  const session = useAtomValue(sessionFilterAtom);
  const { data: store, isLoading } = useEventStore(session);
  // Only the unfiltered store can prove there is nothing to show. With a
  // session selected, an empty result is a filter outcome — keep the toolbar
  // on screen so it can be changed.
  const isEmpty = session === undefined && (store?.events.length ?? 0) === 0;

  const setSnackbar = useSetAtom(snackbarMessageAtom);
  const clearMutation = useClearEvents({
    onSuccess: () => setSnackbar("All events cleared"),
  });

  useHotkeys("mod+shift+e", (e) => {
    e.preventDefault();
    if (!clearMutation.isPending) clearMutation.mutate();
  });

  if (isLoading) {
    return <SplitViewSkeleton />;
  }

  if (isEmpty) {
    return <EmptyState />;
  }

  return (
    <Stack sx={{ height: "100%" }}>
      <Stack
        direction="row"
        alignItems="center"
        sx={{
          bgcolor: neutralSurface,
          color: neutral.textPrimary,
          borderBottom: `1px solid ${neutral.border}`,
        }}
      >
        <Box
          component="a"
          href="/"
          aria-label="TraceLoom home"
          sx={{ display: "flex", alignItems: "center", pl: 1.5, pr: { xs: 0.5, md: 1.5 } }}
        >
          <BrandMark showTagline />
        </Box>
        <Box sx={{ flex: 1 }}>
          <FilterBar />
        </Box>
        <Button
          size="small"
          variant="outlined"
          startIcon={<DeleteIcon />}
          onClick={() => clearMutation.mutate()}
          disabled={clearMutation.isPending}
          sx={{
            mr: 1,
            textTransform: "none",
            height: 40,
            color: "#b3261e",
            borderColor: "rgba(179,38,30,0.35)",
            "&:hover": {
              borderColor: "#b3261e",
              bgcolor: "rgba(179,38,30,0.06)",
            },
          }}
        >
          清空全部 Clear All
        </Button>
      </Stack>
      <Stack direction="row" sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        <Box
          component="nav"
          aria-label="TraceLoom navigation"
          sx={{
            width: { xs: 48, sm: 56 },
            flexShrink: 0,
            borderRight: `1px solid ${neutral.border}`,
            bgcolor: neutralSurface,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            py: 1.25,
            gap: 2,
          }}
        >
          <Box component="a" href="/" aria-label="TraceLoom home" sx={{ display: "flex" }}>
            <BrandMark symbolOnly />
          </Box>
          <Tooltip title="事件流 Event Stream" placement="right">
            <Box
              component="a"
              href="/"
              aria-current="page"
              aria-label="事件流 Event Stream"
              sx={{
                width: 34,
                minHeight: 38,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                color: neutral.textPrimary,
                textDecoration: "none",
                borderLeft: `2px solid ${neutral.textPrimary}`,
                bgcolor: neutral.selected,
              }}
            >
              <EventNoteOutlinedIcon sx={{ fontSize: 18 }} />
              <Typography sx={{ fontSize: 9, lineHeight: 1.1, mt: 0.25 }}>事件 Events</Typography>
            </Box>
          </Tooltip>
        </Box>
        <Group
          orientation="horizontal"
          defaultLayout={initialLayout}
          onLayoutChanged={onLayoutChanged}
          style={{ flex: 1, minWidth: 0, overflow: "hidden" }}
        >
          <Panel id="list" defaultSize="15%" minSize="15%" maxSize="50%">
            <RequestList />
          </Panel>
          <ResizeHandle />
          <Panel id="detail" minSize="30%">
            <Box sx={{ height: "100%", minHeight: 0, overflow: "auto" }}>
              {selectedId ? (
                <RequestDetail requestId={selectedId} />
              ) : (
                <Stack
                  alignItems="center"
                  justifyContent="center"
                  spacing={1}
                  sx={{ height: "100%", color: "text.disabled" }}
                >
                  <Typography>选择一个事件查看详情 · Select an event</Typography>
                  <ButtonBase
                    disableRipple
                    onClick={() => setHelpOpen(true)}
                    sx={{ borderRadius: 1, "&:hover": { color: "text.secondary" } }}
                  >
                    <Typography variant="body2">
                      按 Press{" "}
                      <Kbd
                        sx={{
                          color: "text.disabled",
                          borderColor: "divider",
                          bgcolor: "transparent",
                        }}
                      >
                        ?
                      </Kbd>{" "}
                      查看键盘快捷键 for keyboard shortcuts
                    </Typography>
                  </ButtonBase>
                </Stack>
              )}
            </Box>
          </Panel>
        </Group>
      </Stack>
      <ButtonBase
        disableRipple
        onClick={() => setHelpOpen(true)}
        sx={{
          position: "fixed",
          bottom: 12,
          right: 16,
          display: "flex",
          alignItems: "center",
          gap: 0.5,
          px: 1,
          py: 0.5,
          borderRadius: 1,
          color: "text.disabled",
          "&:hover": { color: "text.secondary", bgcolor: "action.hover" },
          transition: "color 150ms, background-color 150ms",
        }}
      >
        <Kbd sx={{ color: "text.disabled", borderColor: "divider", bgcolor: "transparent" }}>?</Kbd>
        <Typography variant="caption" sx={{ fontSize: 11 }}>
          快捷键 Shortcuts
        </Typography>
      </ButtonBase>
    </Stack>
  );
}
