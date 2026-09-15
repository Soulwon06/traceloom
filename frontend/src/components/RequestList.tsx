import { Fragment, useMemo } from "react";
import { useAtom, useAtomValue } from "jotai";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Typography from "@mui/material/Typography";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import { neutralSurface, neutral } from "../theme";
import type { EventSummary } from "../api/events";
import { groupingModeAtom } from "../atoms/grouping";
import { collapsedHierarchyNodeIdsAtom } from "../atoms/hierarchy";
import { availableGroupingOptions } from "../hierarchy/definitions";
import {
  buildHierarchyProjection,
  countHierarchyEvents,
  type HierarchyNode,
  type MembershipGroupNode,
  type OperationNode,
} from "../hierarchy/grouping";
import { useSelectedRequestId } from "../hooks/useSelectedRequestId";
import { useFilteredRequests } from "../hooks/useFilteredRequests";
import RequestListItem from "./RequestListItem";

const hierarchyBaseIndent = 1;
const hierarchyLevelIndent = 1.5;

function hierarchyIndent(depth: number): number {
  return hierarchyBaseIndent + depth * hierarchyLevelIndent;
}

export default function RequestList() {
  const [selectedId, setSelectedId] = useSelectedRequestId();
  const { data: requests = [] } = useFilteredRequests();
  const groupingMode = useAtomValue(groupingModeAtom);
  const availableModes = availableGroupingOptions(requests);
  const effectiveMode = availableModes.some((option) => option.value === groupingMode)
    ? groupingMode
    : "none";
  const hierarchyProjection = useMemo(
    () => buildHierarchyProjection(requests, effectiveMode),
    [requests, effectiveMode],
  );
  const [collapsed, setCollapsed] = useAtom(collapsedHierarchyNodeIdsAtom);

  const toggle = (id: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const renderEvent = (item: EventSummary, depth = 0) => (
    <Box key={item.id} sx={{ pl: hierarchyIndent(depth) }}>
      <RequestListItem
        item={item}
        selected={item.id === selectedId}
        onClick={() => setSelectedId(item.id)}
      />
    </Box>
  );

  const renderGroup = (node: MembershipGroupNode, depth = 0): React.ReactNode => {
    const isCollapsed = collapsed.has(node.id);
    const loadedCount = countHierarchyEvents(node);
    return (
      <Fragment key={node.id}>
        <ListItemButton
          data-group-id={node.id}
          onClick={() => toggle(node.id)}
          sx={{ minHeight: 34, pl: hierarchyIndent(depth), color: neutral.textSecondary }}
        >
          {isCollapsed ? (
            <ChevronRightIcon fontSize="small" />
          ) : (
            <ExpandMoreIcon fontSize="small" />
          )}
          <FolderOutlinedIcon sx={{ ml: 0.5, mr: 1, fontSize: 17, color: neutral.textMuted }} />
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {node.label}
          </Typography>
          <Typography variant="caption" sx={{ color: neutral.textDisabled }}>
            <Box component="span">{loadedCount} 条已加载记录</Box>{" · "}
            <Box component="span">{loadedCount} loaded {loadedCount === 1 ? "record" : "records"}</Box>
          </Typography>
        </ListItemButton>
        {!isCollapsed && <>{node.children.map((child) => renderHierarchyNode(child, depth + 1))}</>}
      </Fragment>
    );
  };

  const renderRuntimeNode = (node: OperationNode, depth = 0): React.ReactNode => {
    const isCollapsed = collapsed.has(node.id);
    const hasChildren = node.children.length > 0 || node.annotations.length > 0;
    return (
      <Fragment key={node.id}>
        <Box sx={{ position: "relative" }}>
          {hasChildren && (
            <ListItemButton
              aria-label={isCollapsed ? "Expand operation" : "Collapse operation"}
              onClick={() => toggle(node.id)}
              sx={(theme) => ({
                position: "absolute",
                zIndex: 1,
                left: theme.spacing(hierarchyIndent(depth)),
                top: 6,
                p: 0,
              })}
            >
              {isCollapsed ? (
                <ChevronRightIcon fontSize="small" />
              ) : (
                <ExpandMoreIcon fontSize="small" />
              )}
            </ListItemButton>
          )}
          {renderEvent(node.event, depth + 1)}
          {(node.incomplete || node.ambiguous) && (
            <Typography
              variant="caption"
              sx={{ display: "block", pl: hierarchyIndent(depth + 1), color: "#FFA600" }}
            >
              {node.ambiguous
                ? "运行时身份不明确 Ambiguous runtime identity"
                : "父级不在当前加载记录中 Parent not in loaded records"}
            </Typography>
          )}
        </Box>
        {!isCollapsed && (
          <>
            {node.annotations.map((event) => renderEvent(event, depth + 2))}
            {node.children.map((child) => renderHierarchyNode(child, depth + 1))}
          </>
        )}
      </Fragment>
    );
  };

  const renderHierarchyNode = (node: HierarchyNode, depth = 0): React.ReactNode => {
    if (node.kind === "group") return renderGroup(node, depth);
    if (node.kind === "operation") return renderRuntimeNode(node, depth);
    return renderEvent(node.event, depth + 1);
  };

  return (
    <Stack sx={{ height: "100%", bgcolor: neutralSurface, color: neutral.textPrimary }}>
      <Box sx={{ px: 1.5, py: 1, borderBottom: `1px solid ${neutral.border}` }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600 }}>事件流</Typography>
        <Typography sx={{ fontSize: 10, color: neutral.textSecondary, mt: 0.15 }}>
          Event Stream
        </Typography>
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", overscrollBehavior: "none" }}>
        {requests.length === 0 ? (
          <Stack
            alignItems="center"
            justifyContent="center"
            sx={{ height: "100%", p: 3, color: neutral.textMuted }}
          >
            <Typography variant="body2">没有找到匹配的事件</Typography>
            <Typography variant="caption" sx={{ mt: 0.5, color: neutral.textDisabled }}>
              尝试修改搜索词或筛选条件。
            </Typography>
          </Stack>
        ) : (
          <List disablePadding>
            {hierarchyProjection.nodes.map((node) => renderHierarchyNode(node))}
          </List>
        )}
      </Box>
    </Stack>
  );
}
