# Keyboard Shortcuts

TraceLoom supports keyboard shortcuts for fast navigation, inspired by Gmail and Linear. Press <kbd>?</kbd> anywhere in the dashboard to see all available shortcuts.

## General

| Key | Action |
|-----|--------|
| <kbd>?</kbd> | Show keyboard shortcuts |
| <kbd>/</kbd> | Focus search |
| <kbd>Esc</kbd> | Dismiss dialog / blur search / clear selection |

## Navigation

| Key | Action |
|-----|--------|
| <kbd>j</kbd> or <kbd>↓</kbd> | Next visible event |
| <kbd>k</kbd> or <kbd>↑</kbd> | Previous visible event |
| <kbd>→</kbd> | Expand the selected operation or move to its first child |
| <kbd>←</kbd> | Collapse the selected operation or move to its parent |
| <kbd>Backspace</kbd> | Clear selection |

Navigation follows the visible tree. Up and Down skip events inside collapsed runtime
operations or virtual groups. Right expands before moving into a child. Left collapses
before moving to a runtime parent.

## Filters

| Key | Action |
|-----|--------|
| <kbd>Shift</kbd>+<kbd>X</kbd> | Clear all filters |

## Detail Panel

These shortcuts are active when a request is selected.

| Key | Action |
|-----|--------|
| <kbd>q</kbd> | Toggle query parameters |
| <kbd>h</kbd> | Toggle request headers |
| <kbd>H</kbd> | Toggle response headers |
| <kbd>b</kbd> | Toggle request body |
| <kbd>B</kbd> | Toggle response body |
| <kbd>c</kbd> | Copy request body |
| <kbd>C</kbd> | Copy response body |
