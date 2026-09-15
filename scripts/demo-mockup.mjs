#!/usr/bin/env node
/**
 * End-to-end demo mockup generator.
 *
 * 1. Clears all TraceLoom data via the API
 * 2. Runs the pytest hierarchy example, or a custom Python demo
 * 3. Selects an HTTP operation so its runtime context and details are visible
 * 4. Applies Test file grouping for the default hierarchy demo
 * 5. Calls generateMockup() to produce the final screenshot
 *
 * The default pytest example contains an intentional assertion failure, so a non-zero
 * exit code is expected and not treated as a screenshot failure.
 *
 * Usage:
 *   node scripts/demo-mockup.mjs                          # default settings
 *   node scripts/demo-mockup.mjs --dark                   # dark chrome
 *   node scripts/demo-mockup.mjs --output hero.png        # custom output
 *   node scripts/demo-mockup.mjs --script my-script.py    # custom Python demo
 *
 * All mockup options (--output, --dark, --width, etc.) are supported.
 */

import { spawn } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { generateMockup } from "./lib/mockup.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const TRACELOOM_API = process.env.TRACELOOM_URL || "http://localhost:5110";
const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:5111";

// ---------------------------------------------------------------------------
// TraceLoom API helpers
// ---------------------------------------------------------------------------

async function traceloomAPI(path, { method = "GET", expect } = {}) {
  const res = await fetch(`${TRACELOOM_API}${path}`, { method });
  if (expect && res.status !== expect) {
    throw new Error(
      `${method} ${path} returned ${res.status}, expected ${expect}`,
    );
  }
  if (res.status === 204) return null;
  return res.json();
}

async function clearRequests() {
  await traceloomAPI("/api/events", { method: "DELETE", expect: 204 });
  console.log("Cleared all TraceLoom requests.");
}

async function waitForRequests(minCount = 1, timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const { events } = await traceloomAPI(
      `/api/events?event_type=http&limit=${minCount}`,
    );
    if (events.length >= minCount) return events;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(
    `Timed out waiting for at least ${minCount} request(s) in TraceLoom`,
  );
}

// ---------------------------------------------------------------------------
// Demo script runner
// ---------------------------------------------------------------------------

function runDemoScript(scriptPath) {
  return new Promise((resolve) => {
    const command = scriptPath
      ? ["run", "python", scriptPath]
      : [
          "run",
          "traceloom",
          "run",
          "--capture-logs",
          "--log-level",
          "WARNING",
          "--session",
          "screenshot",
          "--",
          "pytest",
          "examples/python/test_pytest_tracking.py",
          "-q",
        ];
    console.log(
      scriptPath
        ? `Running ${scriptPath}...`
        : "Running the pytest hierarchy screenshot demo...",
    );
    const child = spawn("uv", command, {
      cwd: ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));

    // Default and custom demos may fail intentionally to populate failure details.
    child.on("close", (code) => {
      if (stdout) console.log(stdout.trimEnd());
      if (stderr) console.error(stderr.trimEnd());
      if (code !== 0) {
        console.log(`(demo script exited with code ${code} — continuing)`);
      }
      resolve();
    });
  });
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const { values: args } = parseArgs({
  options: {
    // Own options
    script: { type: "string" },
    "select-method": { type: "string", default: "POST" },
    // Mockup options (forwarded to generateMockup)
    url: { type: "string" },
    output: {
      type: "string",
      default: resolve(ROOT, "docs", "assets", "screenshot.png"),
    },
    width: { type: "string", default: "1200" },
    height: { type: "string", default: "750" },
    dark: { type: "boolean", default: false },
    "address-bar": { type: "string", default: "localhost:5110" },
    wait: { type: "string", default: "3000" },
    help: { type: "boolean", short: "h", default: false },
  },
});

if (args.help) {
  console.log(`
Usage: node scripts/demo-mockup.mjs [options]

Demo options:
  --script <path>       Run a custom Python demo instead of the pytest hierarchy demo
  --select-method <m>   HTTP method to pre-select in the dashboard (default: POST).
                        Falls back to the most recent request if none match.

Mockup options:
  --url <url>           Override the screenshot URL (default: auto-detected from frontend)
  --output <path>       Output path (default: docs/assets/screenshot.png)
  --width <px>          Viewport width (default: 1200)
  --height <px>         Viewport height (default: 750)
  --dark                Dark browser chrome
  --address-bar <text>  Text in the address bar (default: localhost:5110)
  --wait <ms>           Wait time after page load (default: 3000)

Environment variables:
  TRACELOOM_URL            TraceLoom API base URL (default: http://localhost:5110)
  FRONTEND_URL          Frontend URL to screenshot (default: http://localhost:5111)
`);
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // 1. Clear
  await clearRequests();

  // 2. Run demo script
  await runDemoScript(args.script);

  // 3. Wait for captures and pick a request — prefer the configured method
  //    (POST by default) since it shows request + response bodies, then fall
  //    back to the most recent capture.
  await waitForRequests(1);
  const { events: requests } = await traceloomAPI(
    "/api/events?event_type=http&limit=50",
  );
  const wantedMethod = args["select-method"].toUpperCase();
  const matchPrefix = `${wantedMethod} `;
  const picked =
    requests.find((r) => (r.summary || "").startsWith(matchPrefix)) ||
    requests[0];
  console.log(`Using request ${picked.id} (${picked.summary})\n`);

  const preparePage = args.script
    ? undefined
    : async (page) => {
        await page.click('[role="combobox"]');
        await page.waitForSelector('[data-value="pytest:test_file"]');
        await page.click('[data-value="pytest:test_file"]');
      };

  // 4. Generate mockup with the request selected and hierarchy grouping applied.
  await generateMockup({
    url: args.url || `${FRONTEND_URL}/#${picked.id}`,
    output: args.output,
    width: parseInt(args.width),
    height: parseInt(args.height),
    dark: args.dark,
    addressBar: args["address-bar"],
    wait: parseInt(args.wait),
    preparePage,
  });
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
