import { render, screen, within, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, afterEach } from "vitest";
import { Provider, createStore } from "jotai";
import { hotkeyHelpOpenAtom } from "../../atoms/hotkeyHelp";
import HotkeyHelpDialog from "../HotkeyHelpDialog";

afterEach(async () => {
  // MUI Dialog uses react-transition-group which sets timeouts for
  // enter/exit transitions (~225ms). Wait for them to complete before
  // cleanup tears down jsdom, otherwise the callbacks fire after teardown
  // and crash with "window is not defined".
  await new Promise((resolve) => setTimeout(resolve, 300));
  cleanup();
});

function renderDialog(open = false) {
  const store = createStore();
  store.set(hotkeyHelpOpenAtom, open);
  return {
    store,
    ...render(
      <Provider store={store}>
        <HotkeyHelpDialog />
      </Provider>,
    ),
  };
}

describe("HotkeyHelpDialog", () => {
  it("is hidden when atom is false", () => {
    renderDialog(false);
    expect(screen.queryByText("Keyboard Shortcuts")).not.toBeInTheDocument();
  });

  it("renders all groups when open", () => {
    renderDialog(true);
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    expect(screen.getByText("通用 General")).toBeInTheDocument();
    expect(screen.getByText("导航 Navigation")).toBeInTheDocument();
    expect(screen.getByText("筛选 Filters")).toBeInTheDocument();
    expect(screen.getByText("详情 Detail")).toBeInTheDocument();
  });

  it("lists shortcut descriptions", () => {
    renderDialog(true);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("显示键盘快捷键")).toBeInTheDocument();
    expect(within(dialog).getByText("聚焦搜索")).toBeInTheDocument();
    expect(within(dialog).getByText("下一个事件")).toBeInTheDocument();
    expect(within(dialog).getByText("展开或收起请求头")).toBeInTheDocument();
  });

  it("closes when close button is clicked", async () => {
    const { store } = renderDialog(true);
    const closeButton = screen.getByRole("button");
    await userEvent.click(closeButton);
    expect(store.get(hotkeyHelpOpenAtom)).toBe(false);
  });
});
