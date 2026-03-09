import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import process from "node:process";
import test, { after, before } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { JSDOM, VirtualConsole } from "jsdom";

const FIXTURE_TIME_ZONE = "UTC";
const HYDRATION_ERROR_PATTERN =
  /hydration|did not match|server rendered html|recoverable error|text content does not match/i;

process.env.TZ = FIXTURE_TIME_ZONE;

const PORT = Number(process.env.PORT ?? "3101");
const HOST = "127.0.0.1";
const BASE_URL = `http://${HOST}:${PORT}`;
const BACKEND_PORT = Number(process.env.TEST_BACKEND_PORT ?? "4101");
const BACKEND_URL = `http://${HOST}:${BACKEND_PORT}`;
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

let currentReadinessScenario = "success";
let currentRuntimeScenario = "success";
let backendServer;

const readinessFixtures = {
  success: {
    settingsStatus: 200,
    settings: {
      contract_version: "1.0.0",
      ownership: [],
      project_settings: [
        {
          key: "DATABASE_URL",
          label: "Backend database URL",
          owner: "agentic-workflow",
          source: "project-env",
          configured: true,
          required: true,
          secret: false,
          value: "sqlite:///runtime.db",
          notes: [],
        },
      ],
      worker_settings: [
        {
          key: "workers.OPENCLAW_WORKSPACE_DIR",
          label: "Worker workspace root",
          owner: "workspace",
          source: "workers-env",
          configured: true,
          required: true,
          secret: false,
          value: "/workspace",
          notes: [],
        },
        {
          key: "workers.DATABASE_URL",
          label: "Worker database URL",
          owner: "agentic-workflow",
          source: "workers-env",
          configured: true,
          required: true,
          secret: false,
          value: "sqlite:///worker.db",
          notes: [],
        },
      ],
      openclaw_settings: [
        {
          key: "gateway.url",
          label: "Gateway URL",
          owner: "gateway",
          source: "openclaw-config",
          configured: true,
          required: true,
          secret: false,
          value: "gateway.local:18789",
          notes: [],
        },
      ],
      validation: {
        valid: true,
        issues: [],
      },
    },
  },
  warning: {
    settingsStatus: 200,
    settings: {
      contract_version: "1.0.0",
      ownership: [],
      project_settings: [
        {
          key: "DATABASE_URL",
          label: "Backend database URL",
          owner: "agentic-workflow",
          source: "project-env",
          configured: true,
          required: true,
          secret: false,
          value: "sqlite:///runtime.db",
          notes: [],
        },
      ],
      worker_settings: [
        {
          key: "workers.OPENCLAW_WORKSPACE_DIR",
          label: "Worker workspace root",
          owner: "workspace",
          source: "workers-env",
          configured: true,
          required: true,
          secret: false,
          value: "/workspace",
          notes: [],
        },
      ],
      openclaw_settings: [],
      validation: {
        valid: true,
        issues: [
          {
            severity: "warning",
            field: "workers.OPENCLAW_WORKSPACE_DIR",
            owner: "workspace",
            code: "worker_workspace_dir_differs",
            message: "Worker workspace directory differs from the backend process view.",
            source: "workers-env",
          },
        ],
      },
    },
  },
  error: {
    settingsStatus: 422,
    settings: {
      error: {
        code: "settings_validation_failed",
        message: "Configuration validation failed.",
        details: {
          validation: {
            valid: false,
            issues: [
              {
                severity: "error",
                field: "OPENCLAW_CONFIG_PATH",
                owner: "openclaw",
                code: "openclaw_config_missing",
                message: "OpenClaw config file was not found.",
                source: "openclaw-config",
              },
            ],
          },
        },
      },
    },
  },
};

const gatewayContractFixture = {
  contract_version: "1.2.0",
  architecture_flow: "frontend -> Agentic-Workflow backend -> Gateway",
  runtime_mode: "multi-agent",
  named_agents: [],
  authority_boundary: [],
  frontend_boundary: {
    flow: "frontend -> /api/v1/gateway/* -> Gateway",
    direct_browser_gateway_access: false,
    notes: [],
  },
  canonical_interfaces: [],
  transport_target: {
    configured: true,
    url: "gateway.local:18789",
    scheme: "wss",
    allow_insecure_tls: false,
    token_configured: true,
    source: "openclaw-config",
    notes: [],
  },
  dependency_chain: [],
  constraints: [],
  event_envelope: {
    version: "v1",
    channel: "backend-bridge",
    delivery: "backend-mediated",
    fields: [],
    notes: [],
  },
};

const gatewayRuntimeFixture = {
  contract_version: "1.2.0",
  availability: "available",
  runtime: {
    source_of_truth: "agentic-workflow+gateway",
    runtime_mode: "multi-agent",
    gateway_url: "gateway.local:18789",
    connection_state: "reserved",
    status: "unknown",
    route_owner: "/api/v1/gateway/runtime",
    agent_states: [
      {
        agent_key: "overlord",
        display_name: "Overlord",
        agent_role: "control-plane-coordinator",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "reserved",
          pending_items: null,
          notes: [
            "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories.",
          ],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: "reserved-session-overlord",
          route_key: "agent.overlord",
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "firehose",
        display_name: "Firehose",
        agent_role: "repository-intake-firehose",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "live",
          source_of_truth: "agentic-workflow",
          pending_items: 7,
          total_items: 10,
          state_counts: {
            pending: 7,
            in_progress: 1,
            completed: 1,
            failed: 1,
          },
          // Fixed Story 2.6 fixture timestamps keep the overview assertions deterministic.
          checkpoint: {
            kind: "firehose",
            next_page: 4,
            last_checkpointed_at: "2026-03-07T10:15:00Z",
            mirror_snapshot_generated_at: "2026-03-07T10:16:00Z",
            active_mode: "trending",
            resume_required: true,
            new_anchor_date: "2026-03-05",
            trending_anchor_date: "2026-02-28",
            run_started_at: "2026-03-07T09:00:00Z",
            window_start_date: null,
            created_before_boundary: null,
            created_before_cursor: null,
            exhausted: null,
          },
          notes: [],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: "reserved-session-firehose",
          route_key: "agent.firehose",
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "backfill",
        display_name: "Backfill",
        agent_role: "repository-intake-backfill",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "live",
          source_of_truth: "agentic-workflow",
          pending_items: 2,
          total_items: 5,
          state_counts: {
            pending: 2,
            in_progress: 1,
            completed: 2,
            failed: 0,
          },
          checkpoint: {
            kind: "backfill",
            next_page: 3,
            last_checkpointed_at: "2026-03-07T09:45:00Z",
            mirror_snapshot_generated_at: "2026-03-07T09:46:00Z",
            active_mode: null,
            resume_required: null,
            new_anchor_date: null,
            trending_anchor_date: null,
            run_started_at: null,
            window_start_date: "2025-01-01",
            created_before_boundary: "2025-01-31",
            created_before_cursor: "2025-01-15T12:00:00Z",
            exhausted: false,
          },
          notes: [],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: "reserved-session-backfill",
          route_key: "agent.backfill",
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "bouncer",
        display_name: "Bouncer",
        agent_role: "repository-triage",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "reserved",
          pending_items: null,
          notes: [
            "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories.",
          ],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: "reserved-session-bouncer",
          route_key: "agent.bouncer",
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "analyst",
        display_name: "Analyst",
        agent_role: "repository-analysis",
        lifecycle_state: "planned",
        mvp_scope: "initial",
        queue: {
          status: "reserved",
          pending_items: null,
          notes: [
            "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories.",
          ],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: "reserved-session-analyst",
          route_key: "agent.analyst",
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "combiner",
        display_name: "Combiner",
        agent_role: "idea-synthesis",
        lifecycle_state: "reserved",
        mvp_scope: "reserved",
        queue: {
          status: "reserved",
          pending_items: null,
          notes: [
            "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories.",
          ],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: null,
          route_key: null,
          status: "reserved",
        },
        notes: [],
      },
      {
        agent_key: "obsession",
        display_name: "Obsession",
        agent_role: "idea-tracking",
        lifecycle_state: "reserved",
        mvp_scope: "reserved",
        queue: {
          status: "reserved",
          pending_items: null,
          notes: [
            "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories.",
          ],
        },
        monitoring: {
          status: "reserved",
          last_heartbeat_at: null,
          notes: [],
        },
        session_affinity: {
          source_of_truth: "gateway",
          session_id: null,
          route_key: null,
          status: "reserved",
        },
        notes: [],
      },
    ],
    notes: [
      "The runtime surface keeps Gateway routing metadata and Agentic-Workflow intake data on one backend-owned contract.",
    ],
  },
};

const runtimeFixtures = {
  success: {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(gatewayRuntimeFixture),
  },
  unavailable: {
    status: 500,
    contentType: "application/json",
    body: JSON.stringify({
      error: {
        code: "gateway_runtime_unavailable",
        message: "Gateway runtime lookup failed.",
      },
    }),
  },
  malformed: {
    status: 200,
    contentType: "application/json",
    body: "{ invalid json",
  },
};

const UTC_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: FIXTURE_TIME_ZONE,
});

const pages = [
  {
    path: "/overview",
    heading: "Overview",
    body: /Pipeline Flow/,
  },
  {
    path: "/repositories",
    heading: "Browse analyzed repositories",
    body: /Filter by source, triage, analysis state/,
  },
  {
    path: "/repositories/demo-repo",
    heading: "Repository Detail",
    body: /Placeholder for canonical page model\./,
  },
  { path: "/ideas", heading: "Ideas", body: /Placeholder for canonical page model\./ },
  {
    path: "/agents",
    heading: "Agents",
    body: /Placeholder for the future agent-management surface\./,
  },
  {
    path: "/incidents",
    heading: "Incidents",
    body: /Placeholder for canonical page model\./,
  },
  {
    path: "/settings",
    heading: "System Readiness",
    body: /Workspace prerequisites, Gateway connectivity, and Project Runtime validation\./,
  },
];

let serverProcess;
let serverLogs = "";

before(async () => {
  backendServer = createServer((req, res) => {
    const fixture = readinessFixtures[currentReadinessScenario];

    if (req.url === "/api/v1/settings/summary") {
      res.writeHead(fixture.settingsStatus, { "content-type": "application/json" });
      res.end(JSON.stringify(fixture.settings));
      return;
    }

    if (req.url === "/api/v1/gateway/contract") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(gatewayContractFixture));
      return;
    }

    if (req.url === "/api/v1/gateway/runtime") {
      const fixture = runtimeFixtures[currentRuntimeScenario];
      res.writeHead(fixture.status, { "content-type": fixture.contentType });
      res.end(fixture.body);
      return;
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: "Not found" } }));
  });

  await new Promise((resolve) => backendServer.listen(BACKEND_PORT, HOST, resolve));

  serverProcess = spawn(
    npmCommand,
    ["run", "dev", "--", "--hostname", HOST, "--port", String(PORT)],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        NEXT_TELEMETRY_DISABLED: "1",
        NEXT_PUBLIC_API_URL: BACKEND_URL,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  for (const stream of [serverProcess.stdout, serverProcess.stderr]) {
    stream?.on("data", (chunk) => {
      serverLogs += chunk.toString();
      if (serverLogs.length > 8000) {
        serverLogs = serverLogs.slice(-8000);
      }
    });
  }

  await waitForServer();
});

after(async () => {
  if (backendServer) {
    await new Promise((resolve, reject) =>
      backendServer.close((error) => (error ? reject(error) : resolve())),
    );
  }

  if (!serverProcess || serverProcess.exitCode !== null) {
    return;
  }

  const exitPromise = once(serverProcess, "exit");
  serverProcess.kill("SIGTERM");

  try {
    await Promise.race([exitPromise, delay(5000)]);
  } finally {
    if (serverProcess.exitCode === null) {
      serverProcess.kill("SIGKILL");
      await once(serverProcess, "exit");
    }
  }
});

test("landing page exposes scaffold navigation", async () => {
  const html = await fetchPage("/");

  assert.match(html, /Agentic-Workflow Dashboard/);
  assert.match(html, /Local-first intelligent repository discovery and idea synthesis\./);

  for (const path of [
    "/overview",
    "/repositories",
    "/ideas",
    "/agents",
    "/incidents",
    "/settings",
  ]) {
    assert.match(html, new RegExp(`href="${path}"`));
  }
});

test("landing page hydrates without browser-side errors", async () => {
  const page = await openBrowserPage("/");

  try {
    const textContent = normalizeText(page.document.body.textContent ?? "");
    assert.match(textContent, /Agentic-Workflow Dashboard/);
    assert.match(textContent, /Local-first intelligent repository discovery and idea synthesis\./);
    assert.deepEqual(page.hydrationErrors, [], page.consoleMessages.join("\n"));
  } finally {
    page.close();
  }
});

for (const { path, heading, body } of pages) {
  test(`page ${path} renders the scaffold heading`, async () => {
    const html = await fetchPage(path);

    assert.match(html, new RegExp(`>${heading}<`));
    assert.match(html, body);
  });
}

test("settings page shows ready state with reserved gateway placeholder and worker context", async () => {
  currentReadinessScenario = "success";

  const html = await fetchPage("/settings");

  assert.match(html, /Ready for Intake/);
  assert.match(html, /Reserved placeholder/);
  assert.match(html, /Live Gateway connectivity checks land in later runtime stories\./);
  assert.match(html, /Workspace Context/);
  assert.match(html, /Worker workspace root/);
  assert.match(html, /Worker Runtime/);
  assert.match(html, /Worker database URL/);
});

test("overview page renders backend-fed Firehose and Backfill intake status", async () => {
  currentRuntimeScenario = "success";
  const html = await fetchPage("/overview");

  assert.match(html, /Pipeline Flow/);
  assert.match(html, /Auto-refresh every 15 seconds/);
  assert.match(html, /Firehose/);
  assert.match(html, /Backfill/);
  assert.match(html, /10(?:<!-- -->)? persisted repositories/);
  assert.match(html, /5(?:<!-- -->)? persisted repositories/);
  assert.match(html, /Mirror snapshot/);
  assert.match(
    html,
    new RegExp(escapeRegExp(formatFixtureTimestamp("2026-03-07T10:16:00Z"))),
  );
  assert.match(
    html,
    new RegExp(escapeRegExp(formatFixtureTimestamp("2026-03-07T09:46:00Z"))),
  );
  assert.match(
    html,
    new RegExp(
      `Created before cursor<\\/dt><dd class="mt-1 text-sm font-medium text-slate-800">${escapeRegExp(
        formatFixtureTimestamp("2025-01-15T12:00:00Z"),
      )}<\\/dd>`,
    ),
  );
  assert.match(
    html,
    new RegExp(escapeRegExp(formatFixtureTimestamp("2025-01-15T12:00:00Z"))),
  );
  assert.match(html, /Agent Matrix/);
  assert.doesNotMatch(html, /Placeholder for the operator overview\./);
});

test("overview page hydrates with deterministic UTC timestamps", async () => {
  currentRuntimeScenario = "success";

  const page = await openBrowserPage("/overview");

  try {
    const textContent = normalizeText(page.document.body.textContent ?? "");
    assert.match(textContent, /Pipeline Flow/);
    assert.match(textContent, /Times shown in UTC/);
    assert.match(
      textContent,
      new RegExp(escapeRegExp(formatFixtureTimestamp("2026-03-07T10:16:00Z"))),
    );
    assert.match(
      textContent,
      new RegExp(escapeRegExp(formatFixtureTimestamp("2025-01-15T12:00:00Z"))),
    );
    assert.deepEqual(page.hydrationErrors, [], page.consoleMessages.join("\n"));
  } finally {
    page.close();
  }
});

test("overview page renders a fallback when the runtime endpoint returns a 500", async () => {
  currentRuntimeScenario = "unavailable";

  try {
    const html = await fetchPage("/overview");

    assert.match(html, /Pipeline Flow/);
    assert.match(html, /Gateway runtime lookup failed\./);
    assert.match(html, /The initial runtime load failed\. The polling loop will keep retrying automatically\./);
    assert.match(html, /Last updated <!-- -->Waiting for first successful sync/);
    assert.match(html, /Waiting for first successful sync/);
    assert.match(html, /Retry now/);
    assert.doesNotMatch(html, /Runtime Unavailable/);
  } finally {
    currentRuntimeScenario = "success";
  }
});

test("overview page renders a fallback when the runtime payload is malformed", async () => {
  currentRuntimeScenario = "malformed";

  try {
    const html = await fetchPage("/overview");

    assert.match(html, /Pipeline Flow/);
    assert.match(html, /Unable to load backend-owned intake status\./);
    assert.match(html, /The initial runtime load failed\. The polling loop will keep retrying automatically\./);
    assert.match(html, /Last updated <!-- -->Waiting for first successful sync/);
    assert.match(html, /Waiting for first successful sync/);
    assert.match(html, /Retry now/);
    assert.doesNotMatch(html, /Runtime Unavailable/);
  } finally {
    currentRuntimeScenario = "success";
  }
});

test("settings page preserves warning-only readiness without blocking intake", async () => {
  currentReadinessScenario = "warning";

  const html = await fetchPage("/settings");

  assert.match(html, /Ready for Intake/);
  assert.match(html, /Warnings detected, but the system is functional/);
  assert.match(html, /worker_workspace_dir_differs/);
});

test("settings page surfaces structured validation issues instead of backend outage copy", async () => {
  currentReadinessScenario = "error";

  const html = await fetchPage("/settings");

  assert.match(html, /Setup Issues Detected/);
  assert.match(html, /openclaw_config_missing/);
  assert.match(html, /OpenClaw config file was not found\./);
  assert.doesNotMatch(html, /Ensure the backend server is running on localhost\./);
});

async function waitForServer() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (serverProcess.exitCode !== null) {
      throw new Error(`Next dev server exited early.\n${serverLogs}`);
    }

    try {
      const response = await fetch(BASE_URL);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until the dev server is ready.
    }

    await delay(500);
  }

  throw new Error(`Timed out waiting for ${BASE_URL}.\n${serverLogs}`);
}

async function fetchPage(path) {
  const response = await fetch(`${BASE_URL}${path}`);
  const html = await response.text();

  assert.equal(response.status, 200, `${path} failed.\n${html}\n${serverLogs}`);

  return html;
}

async function openBrowserPage(path) {
  const consoleMessages = [];
  const virtualConsole = new VirtualConsole();
  const recordConsoleMessage = (value) => {
    consoleMessages.push(formatConsoleValue(value));
  };

  virtualConsole.on("error", recordConsoleMessage);
  virtualConsole.on("warn", recordConsoleMessage);
  virtualConsole.on("jsdomError", recordConsoleMessage);

  const dom = await JSDOM.fromURL(`${BASE_URL}${path}`, {
    pretendToBeVisual: true,
    resources: "usable",
    runScripts: "dangerously",
    virtualConsole,
    beforeParse(window) {
      installBrowserShims(window, consoleMessages);
    },
  });

  await waitForDocumentLoad(dom.window);
  await delay(1500);

  return {
    close() {
      dom.window.close();
    },
    consoleMessages,
    document: dom.window.document,
    hydrationErrors: consoleMessages.filter((message) => HYDRATION_ERROR_PATTERN.test(message)),
  };
}

function installBrowserShims(window, consoleMessages) {
  Object.defineProperty(window.Document.prototype, "currentScript", {
    configurable: true,
    get() {
      return (
        this.querySelector('script[src*="/_next/static/chunks/"]') ??
        this.querySelector("script")
      );
    },
  });
  defineWindowGlobal(window, "fetch", globalThis.fetch.bind(globalThis));
  defineWindowGlobal(window, "Headers", globalThis.Headers);
  defineWindowGlobal(window, "Request", globalThis.Request);
  defineWindowGlobal(window, "Response", globalThis.Response);
  defineWindowGlobal(window, "AbortController", globalThis.AbortController);
  defineWindowGlobal(window, "TextEncoder", globalThis.TextEncoder);
  defineWindowGlobal(window, "TextDecoder", globalThis.TextDecoder);
  defineWindowGlobal(window, "crypto", globalThis.crypto);
  defineWindowGlobal(window, "structuredClone", globalThis.structuredClone);
  window.ResizeObserver =
    window.ResizeObserver ??
    class ResizeObserver {
      disconnect() {}
      observe() {}
      unobserve() {}
    };
  window.IntersectionObserver =
    window.IntersectionObserver ??
    class IntersectionObserver {
      disconnect() {}
      observe() {}
      unobserve() {}
    };
  window.matchMedia =
    window.matchMedia ??
    (() => ({
      addEventListener() {},
      addListener() {},
      dispatchEvent() {
        return false;
      },
      matches: false,
      media: "",
      removeEventListener() {},
      removeListener() {},
    }));
  window.scrollTo = () => {};

  const OriginalDateTimeFormat = window.Intl.DateTimeFormat;
  function FixedTimeZoneDateTimeFormat(locales, options = {}) {
    return new OriginalDateTimeFormat(locales, {
      ...options,
      timeZone: options.timeZone ?? FIXTURE_TIME_ZONE,
    });
  }
  FixedTimeZoneDateTimeFormat.prototype = OriginalDateTimeFormat.prototype;
  FixedTimeZoneDateTimeFormat.supportedLocalesOf =
    OriginalDateTimeFormat.supportedLocalesOf.bind(OriginalDateTimeFormat);
  window.Intl.DateTimeFormat = FixedTimeZoneDateTimeFormat;

  const originalConsoleError = window.console.error.bind(window.console);
  window.console.error = (...args) => {
    consoleMessages.push(args.map(formatConsoleValue).join(" "));
    return originalConsoleError(...args);
  };
}

async function waitForDocumentLoad(window) {
  if (window.document.readyState === "complete") {
    return;
  }

  await new Promise((resolve) => {
    window.addEventListener("load", resolve, { once: true });
  });
}

function defineWindowGlobal(window, key, value) {
  if (typeof window[key] !== "undefined") {
    return;
  }

  Object.defineProperty(window, key, {
    configurable: true,
    value,
    writable: true,
  });
}

function formatFixtureTimestamp(isoValue) {
  return UTC_DATE_TIME_FORMATTER.format(new Date(isoValue));
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function formatConsoleValue(value) {
  return value instanceof Error ? value.stack ?? value.message : String(value);
}

function normalizeText(value) {
  return value.replace(/\s+/g, " ").trim();
}
