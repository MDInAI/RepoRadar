import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import process from "node:process";
import test, { after, before } from "node:test";
import { setTimeout as delay } from "node:timers/promises";

const PORT = Number(process.env.PORT ?? "3101");
const HOST = "127.0.0.1";
const BASE_URL = `http://${HOST}:${PORT}`;
const BACKEND_PORT = Number(process.env.TEST_BACKEND_PORT ?? "4101");
const BACKEND_URL = `http://${HOST}:${BACKEND_PORT}`;
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

let currentReadinessScenario = "success";
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
  contract_version: "1.1.0",
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
  contract_version: "1.1.0",
  availability: "reserved",
  runtime: {
    source_of_truth: "gateway",
    runtime_mode: "multi-agent",
    gateway_url: "gateway.local:18789",
    connection_state: "reserved",
    status: "unknown",
    route_owner: "/api/v1/gateway/runtime",
    agent_states: [],
    notes: [
      "Story 1.3 makes the normalized runtime contract explicitly multi-agent.",
    ],
  },
};

const pages = [
  {
    path: "/overview",
    heading: "Overview",
    body: /Placeholder for the operator overview\./,
  },
  {
    path: "/repositories",
    heading: "Repositories",
    body: /Placeholder for canonical page model\./,
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
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(gatewayRuntimeFixture));
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
