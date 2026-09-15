# scripts/

Tooling for generating browser-mockup screenshots of the TraceLoom dashboard.

## Quick start

```bash
cd scripts && npm install   # one-time: installs puppeteer-core (~3MB, uses system Chrome)
```

### Generate a demo screenshot (recommended)

Clears TraceLoom, runs the pytest hierarchy example, and captures a mockup with its nested
failed HTTP request selected. The generator switches the dashboard to **Test file**
grouping so the screenshot includes both virtual and runtime hierarchy:

```bash
# Requires: traceloom-server on :5110 and frontend dev server on :5111
node scripts/demo-mockup.mjs
```

Output: `docs/assets/screenshot.png` (transparent background, ready for the landing page).

### Options

```bash
node scripts/demo-mockup.mjs --dark                   # dark browser chrome
node scripts/demo-mockup.mjs --output hero.png         # custom output path
node scripts/demo-mockup.mjs --width 1400 --height 900 # custom viewport
node scripts/demo-mockup.mjs --script my-demo.py       # use a custom Python demo instead
node scripts/demo-mockup.mjs --transparent false        # with branded gradient background
```

### Environment variables

| Variable       | Default                  | Description                     |
|----------------|--------------------------|---------------------------------|
| `TRACELOOM_URL`   | `http://localhost:5110`  | TraceLoom API base URL             |
| `FRONTEND_URL` | `http://localhost:5111`  | Frontend URL to screenshot      |

### Generate a Claude Code session screenshot

Renders a mock Claude Code terminal session and captures it as a PNG with
macOS window chrome:

```bash
node scripts/claude-code-mockup.mjs                          # built-in traceloom demo
node scripts/claude-code-mockup.mjs --session session.json   # custom session
node scripts/claude-code-mockup.mjs --width 900              # custom width
```

Output: `docs/assets/claude-code-screenshot.png` (transparent background).

#### Session JSON format

```json
{
  "cwd": "~/project",
  "model": "claude-sonnet-4-6",
  "project": "my-project",
  "messages": [
    { "role": "user", "text": "What's broken?" },
    { "role": "assistant", "text": "Let me check..." },
    { "role": "tool_call", "tool": "Bash", "header": "npm test", "content": "4 passed" },
    { "role": "tool_call", "tool": "Read", "header": "src/app.py", "collapsed": true },
    { "role": "tool_call", "tool": "Edit", "header": "src/app.py", "diff": { "removed": ["old line"], "added": ["new line"] } },
    { "role": "end", "text": "Sautéed for 2m 15s", "cost": "$0.05" }
  ]
}
```

Message roles: `user`, `assistant` (supports `**bold**` and `` `code` `` in text),
`tool_call` (with `tool`, `header`, optional `content`/`diff`/`collapsed`),
`end` (with `text` and optional `cost`).

## Files

| File                          | Role                                                       |
|-------------------------------|-------------------------------------------------------------|
| `demo-mockup.mjs`             | Entry point — clear, run demo, capture, generate mockup    |
| `claude-code-mockup.mjs`      | Claude Code terminal session mockup generator              |
| `lib/mockup.mjs`              | Library — `generateMockup()` and `findChrome()` exports    |
| `lib/template.mjs`            | HTML/CSS browser chrome template (supports transparent bg)  |
| `lib/claude-code-template.mjs`| HTML/CSS Claude Code terminal mock template                 |
| `lib/colors.mjs`              | TraceLoom brand palette and light/dark chrome color tokens     |
| `assets/claude-code-icon.png` | Claude Code icon (from lobehub/lobe-icons)                  |

## How it works

1. **Clear** — `DELETE /api/events` removes all captured traffic.
2. **Demo** — Runs `examples/python/test_pytest_tracking.py` through `traceloom run`. A
   test emits a warning and catches a failed provider call, which produces a nested
   runtime operation. The example also contains an intentional assertion failure.
3. **Pick** — Polls `GET /api/events?event_type=http` until the failed provider call
   arrives, then uses its event ID for the URL deep link.
4. **Capture** — Puppeteer opens the frontend, applies **Test file** grouping, and
   takes a 2x retina screenshot with the failed HTTP operation selected.
5. **Wrap** — A second Puppeteer page renders the screenshot inside an HTML/CSS
   browser chrome template (macOS traffic lights, address bar, rounded corners).
6. **Save** — The composite is saved as a PNG. When `transparent=true` (default),
   the background is transparent so it blends into any page background.
