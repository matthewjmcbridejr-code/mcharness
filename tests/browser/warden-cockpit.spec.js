const fs = require("fs");
const path = require("path");
const PLAYWRIGHT_TEST_MODULE =
  process.env.MCHARNESS_PLAYWRIGHT_TEST_MODULE || "/root/.hermes/node/lib/node_modules/playwright/test";
const { test, expect } = require(PLAYWRIGHT_TEST_MODULE);

const ROOT = path.resolve(__dirname, "..", "..");
const RUNTIME_DIRS = [
  path.join(ROOT, "_mctable", "workbench"),
  path.join(ROOT, "_mctable", "captain"),
  path.join(ROOT, "_mctable", "mcharness", "artifacts"),
];

function resetRuntimeState() {
  for (const directory of RUNTIME_DIRS) {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function builtinCodexAgent() {
  return {
    id: "codex_cli",
    name: "Codex CLI",
    kind: "cli",
    adapter: "codex_cli",
    enabled: true,
    private_only: true,
    builtin: true,
    user_created: false,
    status: "ready",
    runnable: true,
    lane_id: "codex_cli",
    capabilities: ["live_terminal", "code_editing", "tests", "read_only_inspection"],
  };
}

function agentRegistryTemplatesPayload() {
  return {
    service: "mcharness-control-plane",
    templates: [
      { id: "codex_cli", label: "Codex CLI", kind: "cli", adapter: "codex_cli", registerable: false, runnable: true, builtin: true, requires_config: false },
      { id: "jules_remote", label: "Jules Remote", kind: "remote", adapter: "jules_remote", registerable: true, runnable: false, builtin: false, requires_config: true },
      { id: "agy_cli", label: "AGY CLI Coming Later", kind: "cli", adapter: "agy_cli", registerable: false, runnable: false, builtin: false, requires_config: false },
      { id: "custom_cli", label: "Custom CLI Coming Later", kind: "cli", adapter: "custom_cli", registerable: false, runnable: false, builtin: false, requires_config: false },
      { id: "custom_remote", label: "Custom Remote Coming Later", kind: "remote", adapter: "custom_remote", registerable: false, runnable: false, builtin: false, requires_config: false },
    ],
  };
}

async function fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled = true, registeredAgents = [] }) {
  if (pathname.endsWith("/agents/templates")) {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(agentRegistryTemplatesPayload()),
    });
    return true;
  }
  if (pathname.endsWith("/agents") && method === "GET") {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        service: "mcharness-control-plane",
        registry_write_enabled: registryWriteEnabled,
        agents: [builtinCodexAgent(), ...registeredAgents],
      }),
    });
    return true;
  }
  return false;
}

function normalizeMockCaptainPlan(plan) {
  const steps = (plan.steps || []).map((step, index) => ({
    ...step,
    id: step.id || step.step_id || `step_${index + 1}`,
    step_id: step.step_id || step.id || `step_${index + 1}`,
    status: step.status || "queued",
    agent_id: step.agent_id || step.agent || "codex_cli",
  }));
  return {
    ...plan,
    status: plan.status || "active",
    current_step_id: plan.current_step_id || (steps[0] && steps[0].id),
    repo_id: plan.repo_id || "hybrid-agent-os",
    steps,
  };
}

function nextQueuedMockStepId(plan, afterStepId) {
  const steps = plan.steps || [];
  const index = steps.findIndex((step) => (step.id || step.step_id) === afterStepId);
  for (let i = index + 1; i < steps.length; i += 1) {
    const status = steps[i].status || "queued";
    if (status === "queued" || status === "revised") return steps[i].id || steps[i].step_id;
  }
  return null;
}

async function fulfillCaptainLoopRoute(route, ctx) {
  const url = new URL(route.request().url());
  const { pathname } = url;
  const method = route.request().method();
  const body = route.request().postDataJSON ? route.request().postDataJSON() : null;

  if (pathname.endsWith("/captain/plans/recent") && method === "GET") {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        service: "mcharness-control-plane",
        plans: ctx.activePlan ? [ctx.activePlan] : [],
      }),
    });
    return true;
  }

  let match = pathname.match(/\/captain\/plans\/([^/]+)$/);
  if (match && method === "GET") {
    const planId = decodeURIComponent(match[1]);
    if (!ctx.activePlan || ctx.activePlan.plan_id !== planId) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: `Captain plan not found: ${planId}` }),
      });
      return true;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plan: ctx.activePlan }),
    });
    return true;
  }

  match = pathname.match(/\/captain\/plans\/([^/]+)\/steps\/([^/]+)\/dispatch$/);
  if (match && method === "POST") {
    const stepId = decodeURIComponent(match[2]);
    ctx.dispatchCalls = ctx.dispatchCalls || [];
    ctx.dispatchCalls.push({ stepId, body });
    if (ctx.runnerStartCalls) ctx.runnerStartCalls.push(body);
    const step = (ctx.activePlan?.steps || []).find((item) => (item.id || item.step_id) === stepId);
    const prompt = step?.prompt || "";
    ctx.runnerStatus = { ...ctx.runnerStatus, status: "running" };
    ctx.activePlan = normalizeMockCaptainPlan({
      ...ctx.activePlan,
      steps: (ctx.activePlan.steps || []).map((item) => {
        const id = item.id || item.step_id;
        return id === stepId
          ? { ...item, status: "dispatched", run_id: ctx.runnerStatus.runner_id }
          : item;
      }),
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        plan: ctx.activePlan,
        dispatch: {
          session_id: ctx.runnerStatus.session_id,
          runner_id: ctx.runnerStatus.runner_id,
          prompt,
        },
      }),
    });
    return true;
  }

  match = pathname.match(/\/captain\/plans\/([^/]+)\/steps\/([^/]+)\/complete$/);
  if (match && method === "POST") {
    const stepId = decodeURIComponent(match[2]);
    ctx.completeCalls = ctx.completeCalls || [];
    ctx.completeCalls.push({ stepId, body });
    const nextStepId = nextQueuedMockStepId(ctx.activePlan, stepId);
    ctx.activePlan = normalizeMockCaptainPlan({
      ...ctx.activePlan,
      status: nextStepId ? "active" : "completed",
      current_step_id: nextStepId || stepId,
      steps: (ctx.activePlan.steps || []).map((item) => {
        const id = item.id || item.step_id;
        return id === stepId ? { ...item, status: "passed", evidence_ids: body?.evidence_ids || [] } : item;
      }),
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, plan: ctx.activePlan }),
    });
    return true;
  }

  match = pathname.match(/\/captain\/plans\/([^/]+)\/steps\/([^/]+)\/revise$/);
  if (match && method === "POST") {
    const stepId = decodeURIComponent(match[2]);
    ctx.reviseCalls = ctx.reviseCalls || [];
    ctx.reviseCalls.push({ stepId, body });
    ctx.activePlan = normalizeMockCaptainPlan({
      ...ctx.activePlan,
      steps: (ctx.activePlan.steps || []).map((item) => {
        const id = item.id || item.step_id;
        return id === stepId
          ? { ...item, status: "revised", prompt: body?.prompt || item.prompt, title: body?.title || item.title }
          : item;
      }),
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, plan: ctx.activePlan }),
    });
    return true;
  }

  match = pathname.match(/\/captain\/plans\/([^/]+)\/stop$/);
  if (match && method === "POST") {
    ctx.stopCalls = ctx.stopCalls || [];
    ctx.stopCalls.push(body);
    ctx.activePlan = normalizeMockCaptainPlan({
      ...ctx.activePlan,
      status: "stopped",
      steps: (ctx.activePlan.steps || []).map((item) => {
        const status = item.status || "queued";
        return ["queued", "revised", "dispatched", "running", "needs_review"].includes(status)
          ? { ...item, status: "stopped" }
          : item;
      }),
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, plan: ctx.activePlan }),
    });
    return true;
  }

  return false;
}

test.beforeEach(() => {
  resetRuntimeState();
});

test.afterEach(() => {
  resetRuntimeState();
});

test("proves the minimal Agent Library + Codex flow (SIMPLE MODE)", async ({ page }, testInfo) => {
  await page.route("**/api/mcharness/captain/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        configured: false,
        provider: "openrouter",
        model: "openrouter/auto",
        planning_enabled: false,
        key_source: "missing",
        private_key_setup_enabled: false,
        notes: ["Captain is not configured. Set OPENROUTER_API_KEY on the private service."],
      }),
    });
  });
  await page.goto("/web/warden/index.html");

  // Simple default UI
  await expect(page.locator("h1")).toContainText("Warden");
  await expect(page.locator("[data-testid='warden-byline']")).toContainText("by Marius Systems");
  await expect(page.locator("[data-testid='warden-sidebar']")).toBeVisible();
  await expect(page.locator("[data-testid='warden-powered']")).toContainText("Powered by McHarness");
  await expect(page.locator("[data-testid='nav-mission']")).toHaveClass(/active/);
  await expect(page.locator("[data-testid='warden-section-mission']")).toHaveClass(/active/);
  await expect(page.locator("[data-testid='mission-command']")).toContainText("What do you want Warden to build?");
  await expect(page.locator("[data-testid='mission-command']")).toContainText("Captain breaks goals into bounded agent steps");
  await expect(page.locator("[data-testid='current-mission-card']")).toContainText("No active mission yet");
  await expect(page.locator("[data-testid='mission-worklog-card']")).toContainText("Captain plans, dispatched steps");
  await expect(page.locator("[data-testid='operator-inspector']")).toBeVisible();
  await expect(page.locator("[data-testid='inspector-next-move']")).toContainText("Next Move");
  await expect(page.locator("[data-testid='control-room-status']")).toContainText("Control Room Status");
  await expect(page.locator("[data-testid='cr-public-runner']")).toContainText("Public runner: Disabled");
  await expect(page.locator("[data-testid='inspector-connected-agents']")).toBeVisible();
  await expect(page.locator("[data-testid='develop-plan-primary']")).toBeVisible();
  await expect(page.locator("#warden-section-agents.active")).toHaveCount(0);
  await expect(page.locator("#warden-section-mission.active")).toBeVisible();

  await page.locator("[data-testid='nav-tasks']").click();
  await expect(page.locator("[data-testid='tasks-empty-state']")).toContainText("No active task plan yet");
  await page.locator("[data-testid='nav-runs']").click();
  await expect(page.locator("[data-testid='runs-empty-state']")).toContainText("Runs will show live and completed agent sessions");
  await page.locator("[data-testid='nav-evidence']").click();
  await expect(page.locator("[data-testid='evidence-empty-state']")).toContainText("Saved outputs");
  await page.locator("[data-testid='nav-settings']").click();
  await expect(page.locator("[data-testid='settings-captain-status']")).toContainText("Captain:");
  await expect(page.locator("[data-testid='settings-public-runner']")).toContainText("Public runner: Disabled on public service");
  await expect(page.locator("[data-testid='settings-private-runner']")).toContainText("Private runner:");
  await expect(page.locator("[data-testid='settings-shell-input']")).toContainText("Arbitrary shell input: Disabled");
  await expect(page.locator("[data-testid='settings-agent-registration']")).toContainText("Agent registration:");
  await expect(page.locator("text=SERVER CONTROL PLANE")).toHaveCount(0);
  await expect(page.locator("text=Advanced / Legacy Cockpit")).toHaveCount(0);
  await page.locator("[data-testid='nav-agents']").click();
  await expect(page.locator("text=Agent Library")).toBeVisible();
  await expect(page.locator("[data-testid='operator-inspector']")).toBeVisible();
  await expect(page.locator("[data-testid='agent-group-ready']")).toBeVisible();
  await expect(page.locator("[data-testid='agent-group-ready']")).toContainText("Ready to Run");
  await expect(page.locator("#codex-card")).toBeVisible();
  await expect(page.locator("#codex-card")).toContainText("Codex CLI");
  await expect(page.locator("#codex-card")).toContainText("Run live coding tasks through Warden");
  await expect(page.locator("#codex-card").getByRole("button", { name: "Use Agent" })).toBeVisible();
  await expect(page.locator("#codex-card").getByRole("button", { name: "View Agent" })).toBeVisible();
  await expect(page.locator("[data-testid='agent-library-cards']")).not.toContainText("Open Live Monitor");
  await expect(page.getByRole("button", { name: "Add Agent" })).toBeVisible();
  await expect(page.locator("[data-testid='add-agent-help']")).toContainText("configuration and connection checks");

  await page.locator("[data-testid='view-agent-codex']").click();
  const viewMon = page.locator("#live-cli-modal");
  await expect(viewMon).toBeVisible();
  await expect(viewMon).toContainText("Codex Live Monitor");
  await viewMon.locator("#modal-close").click();
  await expect(viewMon).not.toBeVisible();

  await page.locator("[data-testid='nav-mission']").click();
  await page.locator("[data-testid='develop-plan-hero']").click();
  const captainModal = page.locator("#captain-deck-modal");
  await expect(captainModal).toBeVisible();
  await expect(captainModal.locator("#captain-config-note")).toContainText("Captain is not configured. Set OPENROUTER_API_KEY on the private service.");
  await expect(captainModal.locator("[data-testid='captain-settings-status']")).toContainText("Not configured");
  await expect(captainModal.locator("[data-testid='captain-settings-note']")).toContainText("Captain key setup is available only on the private service.");
  await expect(captainModal.locator("[data-testid='captain-set-key']")).toBeDisabled();
  await expect(captainModal.locator("#captain-create-plan")).toBeDisabled();
  await captainModal.locator("#captain-close").click();
  await expect(captainModal).not.toBeVisible();

  // Use Agent opens modal with required fields
  await page.locator("[data-testid='nav-agents']").click();
  await page.getByRole("button", { name: "Use Agent" }).click();
  const useModal = page.locator("#use-agent-modal");
  await expect(useModal).toBeVisible();
  await expect(useModal.locator("text=Use Codex CLI")).toBeVisible();
  await expect(useModal.locator("#modal-repo-select")).toBeVisible();
  await expect(useModal.locator("#modal-task-title")).toBeVisible();
  await expect(useModal.locator("#modal-prompt")).toBeVisible();
  await expect(useModal.locator("#deploy-prompt-btn")).toBeVisible();
  await expect(useModal.locator("text=Cancel")).toBeVisible();

  // Deploy (public disabled path) shows clear message, no arbitrary input
  await useModal.locator("#modal-task-title").fill("Test task for codex");
  await useModal.locator("#modal-prompt").fill("Print exactly: MCHARNESS_SIMPLE_MODE_PROOF_LINE");
  await useModal.locator("#deploy-prompt-btn").click();

  // Since public runner disabled, the note in the use modal should appear (no real start)
  await expect(useModal.locator("#deploy-disabled-note")).toBeVisible({ timeout: 5000 });
  await expect(useModal.locator("#deploy-disabled-note")).toContainText("Codex runner is disabled");

  // Deploy opens Live Monitor and should close setup modals underneath
  const mon = page.locator("#live-cli-modal").or(page.getByTestId("live-cli-modal"));
  await expect(mon).toBeVisible({ timeout: 10000 });
  await expect(mon).toContainText("Live read-only view. Use the buttons below for safe replies.");

  await mon.locator("#modal-close").or(page.getByTestId("modal-close")).click();
  await expect(mon).not.toBeVisible();
  await expect(useModal).not.toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("cockpit-final.png"), fullPage: true });
});

test("Captain Settings saves a private OpenRouter key and enables Captain planning", async ({ page }) => {
  let captainStatus = {
    ok: true,
    configured: false,
    provider: "openrouter",
    model: "openrouter/auto",
    planning_enabled: false,
    key_source: "missing",
    private_key_setup_enabled: true,
    notes: ["Captain is not configured. Set OPENROUTER_API_KEY on the private service."],
  };
  let transcriptText = "Captain runner idle.\n";
  let runnerStatus = {
    session_id: "captain-settings-session",
    runner_id: "run_captain_settings",
    lane_id: "codex_cli",
    repo_id: "hybrid-agent-os",
    status: "waiting_for_codex",
    tmux_session_name: "mch_captain_settings",
    attach_command: "tmux attach -t mch_captain_settings",
  };
  const runnerStartCalls = [];
  const sendPromptCalls = [];
  const captainLoopCtx = {
    activePlan: null,
    runnerStatus: null,
    runnerStartCalls,
    dispatchCalls: [],
  };
  await page.addInitScript(() => {
    window.__storageWrites = [];
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      window.__storageWrites.push([key, value]);
      return originalSetItem.call(this, key, value);
    };
  });

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;
    captainLoopCtx.runnerStatus = runnerStatus;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          mode: "public_manual",
          real_agent_launch_enabled: false,
          arbitrary_command_execution_enabled: false,
          public_write_enabled: true,
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          available_lanes_count: 7,
          repo_count: 2,
          manual_mode: true,
        }),
      });
      return;
    }

    if (await fulfillCaptainLoopRoute(route, captainLoopCtx)) {
      return;
    }

    if (pathname.endsWith("/agent-lanes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          manual_mode: true,
          lanes: [
            {
              lane_id: "codex_cli",
              title: "Codex CLI",
              installed: true,
              runner_mode: "controlled_run_ready",
              executable_path: "/root/.hermes/node/bin/codex",
              version: "codex-cli 0.137.0",
              auth_status: "likely_ready",
              safety_notes: ["tmux available: True"],
            },
          ],
        }),
      });
      return;
    }

    if (await fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled: true })) {
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          mode: "server_control_plane",
          repos: [
            {
              repo_id: "hybrid-agent-os",
              label: "hybrid-agent-os",
              path: "/root/hybrid-agent-os",
            },
            {
              repo_id: "mcharness-public-export",
              label: "mcharness-public-export",
              path: "/root/mcharness-public-export",
            },
          ],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(captainStatus),
      });
      return;
    }

    if (pathname.endsWith("/captain/key") && method === "POST") {
      captainStatus = {
        ...captainStatus,
        configured: true,
        planning_enabled: true,
        key_source: "saved",
        model: body.model || "openrouter/auto",
        notes: ["Captain is configured via saved private key."],
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          configured: true,
          provider: "openrouter",
          model: captainStatus.model,
          key_source: "saved",
          private_key_setup_enabled: true,
          notes: ["Captain key saved."],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/plan") && method === "POST") {
      const planBody = normalizeMockCaptainPlan({
        ok: true,
        plan_id: "plan_saved_key",
        title: "Captain Saved Key Plan",
        summary: "Plan after saved key setup.",
        repo_id: "hybrid-agent-os",
        steps: [
          {
            id: "step_1",
            title: "Inspect frontend structure",
            agent: "codex_cli",
            prompt: "Exact goal: Create a read-only plan to inspect the McHarness frontend. Do not edit files.\nForbidden actions: no push, merge, reset, rebase, no secrets, no deploy commands.\nAcceptance checks: identify the frontend entrypoints.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
            status: "queued",
          },
          {
            id: "step_2",
            title: "Verify and report",
            agent: "codex_cli",
            prompt: "Exact goal: Create a read-only plan to inspect the McHarness frontend. Do not edit files.\nForbidden actions: no push, merge, reset, rebase, no secrets, no deploy commands.\nAcceptance checks: return a concise proof report.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
            status: "queued",
          },
          {
            id: "step_3",
            title: "Final proof",
            agent: "codex_cli",
            prompt: "Exact goal: Create a read-only plan to inspect the McHarness frontend. Do not edit files.\nForbidden actions: no push, merge, reset, rebase, no secrets, no deploy commands.\nAcceptance checks: finish with proof only.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
            status: "queued",
          },
        ],
        notes: ["OpenRouter model: openrouter/custom"],
      });
      captainLoopCtx.activePlan = planBody;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(planBody),
      });
      return;
    }

    if (pathname.endsWith("/sessions") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: runnerStatus.session_id }),
      });
      return;
    }

    if (pathname.endsWith("/queue") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ queue_item_id: "queue-captain-1" }),
      });
      return;
    }

    if (pathname.endsWith("/prompt-export") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    if (pathname.endsWith("/runner/start") && method === "POST") {
      runnerStartCalls.push(body);
      runnerStatus = { ...runnerStatus, status: "running" };
      captainLoopCtx.runnerStatus = runnerStatus;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-prompt") && method === "POST") {
      sendPromptCalls.push(body.prompt);
      transcriptText = `${transcriptText}\n${body.prompt}\nCaptain response pending.`;
      runnerStatus = { ...runnerStatus, status: "awaiting_response" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          injected: true,
          session_id: runnerStatus.session_id,
          status: runnerStatus.status,
          transcript_excerpt: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: runnerStatus.session_id,
          runner_id: runnerStatus.runner_id,
          lane_id: runnerStatus.lane_id,
          status: runnerStatus.status,
          transcript_path: "/tmp/captain-settings-transcript.txt",
          transcript: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/stop")) {
      runnerStatus = { ...runnerStatus, status: "stopped" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...runnerStatus, stopped_at: new Date().toISOString() }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("http://127.0.0.1:8125/web/warden/index.html");
  await expect(page.locator("[data-testid='develop-plan-primary']")).toBeVisible();

  await page.locator("[data-testid='develop-plan-primary']").click();
  const captainModal = page.locator("#captain-deck-modal");
  await expect(captainModal).toBeVisible();
  await expect(captainModal.locator("[data-testid='captain-set-key']")).toBeVisible();
  await captainModal.locator("[data-testid='captain-set-key']").click();
  await expect(captainModal.locator("[data-testid='captain-key-form']")).toBeVisible();
  await expect(captainModal.locator("[data-testid='captain-openrouter-key']")).toHaveAttribute("type", "password");
  await captainModal.locator("[data-testid='captain-openrouter-key']").fill("sk-or-private-test-key");
  await captainModal.locator("[data-testid='captain-openrouter-model']").fill("openrouter/custom");
  await captainModal.locator("[data-testid='captain-save-key']").click();
  await expect(captainModal.locator("[data-testid='captain-openrouter-key']")).toHaveValue("");
  await expect(captainModal.locator("[data-testid='captain-settings-status']")).toContainText("Configured");
  await expect(captainModal.locator("[data-testid='captain-settings-status']")).toContainText("saved");
  await expect(captainModal.locator("[data-testid='captain-settings-note']")).toContainText("saved private key");
  await expect(captainModal.locator("[data-testid='captain-create-plan']")).toBeEnabled();
  await expect(captainModal.locator("[data-testid='captain-remove-key']")).toBeVisible();
  await expect(captainModal.locator("[data-testid='captain-openrouter-key']")).toBeHidden();
  await captainModal.locator("[data-testid='captain-goal']").fill("Create a read-only plan to inspect the McHarness frontend. Do not edit files.");
  await captainModal.locator("[data-testid='captain-create-plan']").click();
  await expect(captainModal.locator("[data-testid='captain-plan-status']")).toContainText("Plan ready: Captain Saved Key Plan");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Inspect frontend structure");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Verify and report");
  await page.evaluate(() => {
    const original = window.setTimeout;
    window.setTimeout = (fn, ms, ...args) => (ms === 10000 ? original(fn, 0, ...args) : original(fn, ms, ...args));
  });
  await captainModal.locator("[data-testid='captain-deploy-first']").click();
  await expect.poll(() => runnerStartCalls.length).toBe(1);
  await expect.poll(() => sendPromptCalls.length).toBe(1);
  await expect(page.locator("#captain-deck-modal")).not.toBeVisible();
  const mon = page.locator("#live-cli-modal");
  await expect(mon).toBeVisible();
  await expect(page.locator("#live-cli-modal input, #live-cli-modal textarea")).toHaveCount(0);
  await expect(page.locator("#modal-info")).toContainText("Repo: hybrid-agent-os");
  await expect(page.locator("#modal-info")).toContainText("Status: Running");
  await expect(mon.locator("[data-testid='modal-transcript']")).toContainText("Captain response pending.");
  const storageWrites = await page.evaluate(() => window.__storageWrites || []);
  expect(storageWrites).toEqual([]);
});

test("private runner quick replies send allowed keys and refresh transcript", async ({ page }) => {
  const makeTranscript = (count, prefix = "Codex output") =>
    Array.from({ length: count }, (_, idx) => `${prefix} line ${idx + 1}`).join("\n");
  let transcriptText = [
    "Codex update available",
    "",
    "1. Update now",
    "2. Skip",
    "3. Skip until next version",
    "",
    "Press enter to continue",
    "",
    makeTranscript(140, "Initial transcript"),
  ].join("\n");
  let runnerStatus = {
    session_id: "quick-reply-session",
    runner_id: "run_quick_reply",
    lane_id: "codex_cli",
    repo_id: "mcharness-public-export",
    status: "waiting_for_codex",
    tmux_session_name: "mch_quick_reply",
    attach_command: "tmux attach -t mch_quick_reply",
  };
  let sendKeyCalls = [];

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          mode: "public_manual",
          real_agent_launch_enabled: false,
          arbitrary_command_execution_enabled: false,
          public_write_enabled: true,
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          available_lanes_count: 7,
          repo_count: 1,
          manual_mode: true,
        }),
      });
      return;
    }

    if (pathname.endsWith("/agent-lanes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          manual_mode: true,
          lanes: [
            {
              lane_id: "codex_cli",
              title: "Codex CLI",
              installed: true,
              runner_mode: "controlled_run_ready",
              executable_path: "/root/.hermes/node/bin/codex",
              version: "codex-cli 0.137.0",
              auth_status: "likely_ready",
              safety_notes: ["tmux available: True"],
            },
          ],
        }),
      });
      return;
    }

    if (await fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled: true })) {
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          mode: "server_control_plane",
          repos: [
            {
              repo_id: "mcharness-public-export",
              label: "mcharness-public-export",
              path: "/root/mcharness-public-export",
            },
          ],
        }),
      });
      return;
    }

    if (pathname.endsWith("/sessions") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: "quick-reply-session" }),
      });
      return;
    }

    if (pathname.endsWith("/queue") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ queue_item_id: "queue-1" }),
      });
      return;
    }

    if (pathname.endsWith("/prompt-export") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    if (pathname.endsWith("/runner/start") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-prompt") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, injected: true }),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-key") && method === "POST") {
      if (body.key === "Submit / Continue") {
        sendKeyCalls.push("Tab", "Enter");
        runnerStatus = { ...runnerStatus, status: "prompt_sent" };
        transcriptText = `${transcriptText}\n# [submit/continue]\nPrompt sent to Codex.\n`;
      } else {
        sendKeyCalls.push(body.key);
        runnerStatus = { ...runnerStatus, status: "prompt_sent" };
        transcriptText = `${transcriptText}\n# [quick reply ${body.key}]\nSent: ${body.key}\n`;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          session_id: runnerStatus.session_id,
          runner_id: runnerStatus.runner_id,
          lane_id: runnerStatus.lane_id,
          tmux_session_name: runnerStatus.tmux_session_name,
          sent_key: body.key,
          status: runnerStatus.status,
          status_note: body.key === "Submit / Continue" ? "Prompt sent to Codex." : undefined,
          transcript_excerpt: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: runnerStatus.session_id,
          runner_id: runnerStatus.runner_id,
          lane_id: runnerStatus.lane_id,
          status: runnerStatus.status,
          transcript_path: "/tmp/quick-reply-transcript.txt",
          transcript: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/stop")) {
      runnerStatus = { ...runnerStatus, status: "stopped" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...runnerStatus, stopped_at: new Date().toISOString() }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("http://127.0.0.1:8125/web/warden/index.html");
  await page.locator("[data-testid='nav-agents']").click();
  await expect(page.locator("text=Agent Library")).toBeVisible();

  await page.getByRole("button", { name: "Use Agent" }).click();
  const useModal = page.locator("#use-agent-modal");
  await expect(useModal).toBeVisible();
  await useModal.locator("#modal-task-title").fill("Private quick reply smoke");
  await useModal.locator("#modal-prompt").fill("Safe smoke prompt");
  await useModal.locator("#deploy-prompt-btn").click();

  const mon = page.locator("#live-cli-modal");
  await expect(mon).toBeVisible();
  await expect(mon).toContainText("Codex Live Monitor");
  await expect(mon.locator("[data-testid='modal-transcript']")).toBeVisible();
  await expect(mon.locator("[data-testid='modal-transcript']")).toHaveCSS("overflow-y", /auto|scroll/);
  await expect(mon.locator("[data-testid='quick-reply-panel']")).toBeVisible();
  await expect(mon.locator("[data-testid='quick-reply-panel']")).toContainText("Use for Codex menus and approvals.");
  await expect(mon.locator("[data-quick-reply='1']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='2']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='3']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Submit / Continue']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Enter']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Esc']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Ctrl+C']")).toBeVisible();
  await expect(mon.locator("[data-testid='modal-jump-latest']")).toBeVisible();
  await expect(mon.locator("[data-testid='modal-expand']")).toBeVisible();
  await expect(mon.locator("[data-testid='modal-autorefresh']")).toBeVisible();
  await expect(mon.locator("[data-testid='modal-save-evidence']")).toBeVisible();
  await expect(page.locator("#live-cli-modal input, #live-cli-modal textarea")).toHaveCount(0);
  await expect(page.locator("[data-testid='modal-refresh']")).toContainText("Refresh");
  await expect(page.locator("[data-testid='modal-expand']")).toContainText("Bigger View");
  await expect(page.locator("[data-testid='modal-copy-attach']")).toContainText("Copy Terminal Command");
  await expect(page.locator("[data-testid='modal-save-evidence']")).toContainText("Save Output");
  await expect(page.locator("[data-testid='modal-stop']")).toContainText("Stop Codex");

  const transcript = mon.locator("[data-testid='modal-transcript']");
  const initialMetrics = await transcript.evaluate((el) => ({
    scrollTop: el.scrollTop,
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
  }));
  expect(initialMetrics.scrollHeight).toBeGreaterThan(initialMetrics.clientHeight);
  expect(initialMetrics.scrollTop).toBeGreaterThan(0);

  await transcript.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
  await expect(page.locator("[data-testid='modal-autoscroll-indicator']")).toBeVisible();
  await expect(page.locator("[data-testid='modal-autoscroll-indicator']")).toContainText("Scrolled up — updates paused here");

  transcriptText = `${transcriptText}\n${makeTranscript(40, "Follow-up output")}`;
  await page.evaluate(() => window.McHarnessSimple.refreshLiveMonitor());
  await expect.poll(async () => transcript.evaluate((el) => el.scrollTop)).toBe(0);

  await mon.locator("[data-testid='modal-jump-latest']").click();
  await expect(page.locator("[data-testid='modal-autoscroll-indicator']")).toBeHidden();
  await expect.poll(async () => transcript.evaluate((el) => el.scrollTop > 0)).toBe(true);

  await mon.locator("[data-testid='modal-expand']").click();
  await expect(mon).toHaveClass(/monitor-expanded/);
  await mon.locator("[data-testid='modal-expand']").click();
  await expect(mon).not.toHaveClass(/monitor-expanded/);
  await expect(mon.locator("[data-testid='modal-transcript']")).not.toContainText("Prompt appears pasted but no Codex response yet. Try Enter quick reply or attach manually.");
  await expect(page.locator("#modal-info")).toContainText("Repo: mcharness-public-export");
  await expect(page.locator("#modal-info")).toContainText("Status: Running");
  await expect(page.locator("#modal-info")).toContainText("Session: mch_quick_reply");

  await mon.locator("[data-quick-reply='2']").click();
  await expect(page.locator("[data-testid='quick-reply-status']")).toContainText("Sent: 2");
  await expect(page.locator("[data-testid='modal-transcript']")).toContainText("Sent: 2");
  await expect(page.locator("[data-testid='modal-transcript']")).toContainText("quick reply 2");
  await expect.poll(() => sendKeyCalls.length).toBe(1);
  await expect(sendKeyCalls[0]).toBe("2");

  await mon.locator("[data-quick-reply='Enter']").click();
  await expect.poll(() => sendKeyCalls.length).toBe(2);
  await expect(sendKeyCalls[1]).toBe("Enter");
  await expect(page.locator("[data-testid='quick-reply-status']")).toContainText("Sent: Enter");

  await mon.locator("[data-quick-reply='Submit / Continue']").click();
  await expect.poll(() => sendKeyCalls.length).toBe(4);
  await expect(sendKeyCalls.slice(-2)).toEqual(["Tab", "Enter"]);
  await expect(page.locator("[data-testid='quick-reply-status']")).toContainText("Prompt sent to Codex.");
  await expect(page.locator("[data-testid='modal-transcript']")).toContainText("Prompt sent to Codex.");

  await mon.locator("#modal-stop").click();
  await expect.poll(() => runnerStatus.status).toBe("stopped");
});

test("Captain Deck creates a plan and deploys the first prompt", async ({ page }) => {
  let transcriptText = [
    "Captain runner started.",
    "Waiting for first prompt.",
  ].join("\n");
  let runnerStatus = {
    session_id: "captain-plan-session",
    runner_id: "run_captain_plan",
    lane_id: "codex_cli",
    repo_id: "hybrid-agent-os",
    status: "waiting_for_codex",
    tmux_session_name: "mch_captain_plan",
    attach_command: "tmux attach -t mch_captain_plan",
  };
  const runnerStartCalls = [];
  const sendPromptCalls = [];
  const captainLoopCtx = {
    activePlan: null,
    runnerStatus: null,
    runnerStartCalls,
    dispatchCalls: [],
  };
  const captainPlanResponse = normalizeMockCaptainPlan({
    ok: true,
    plan_id: "plan_1234",
    title: "Build AOL-inspired webpage",
    summary: "Create an AOL-inspired homepage layout in the existing frontend.",
    repo_id: "hybrid-agent-os",
    steps: [
      {
        id: "step_1",
        title: "Inspect frontend structure",
        agent: "codex_cli",
        prompt: "Exact goal: Build a webpage just like aol.com\nForbidden actions: no push, merge, reset, rebase.\nAcceptance checks: identify the entrypoint.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
        status: "queued",
      },
      {
        id: "step_2",
        title: "Implement layout",
        agent: "codex_cli",
        prompt: "Exact goal: Build a webpage just like aol.com\nForbidden actions: no push, merge, reset, rebase.\nAcceptance checks: make the requested layout change.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
        status: "queued",
      },
      {
        id: "step_3",
        title: "Verify and report",
        agent: "codex_cli",
        prompt: "Exact goal: Build a webpage just like aol.com\nForbidden actions: no push, merge, reset, rebase.\nAcceptance checks: run the focused checks and report proof.\nFinal proof format: branch, commit hash if any, files changed, tests run/output, and remaining unproven items.",
        status: "queued",
      },
    ],
    notes: ["OpenRouter model: openrouter/auto"],
  });

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;
    captainLoopCtx.runnerStatus = runnerStatus;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          mode: "public_manual",
          real_agent_launch_enabled: false,
          arbitrary_command_execution_enabled: false,
          public_write_enabled: true,
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          available_lanes_count: 7,
          repo_count: 2,
          manual_mode: true,
        }),
      });
      return;
    }

    if (await fulfillCaptainLoopRoute(route, captainLoopCtx)) {
      return;
    }

    if (pathname.endsWith("/agent-lanes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          manual_mode: true,
          lanes: [
            {
              lane_id: "codex_cli",
              title: "Codex CLI",
              installed: true,
              runner_mode: "controlled_run_ready",
              executable_path: "/root/.hermes/node/bin/codex",
              version: "codex-cli 0.137.0",
              auth_status: "likely_ready",
              safety_notes: ["tmux available: True"],
            },
          ],
        }),
      });
      return;
    }

    if (await fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled: true })) {
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          mode: "server_control_plane",
          repos: [
            {
              repo_id: "hybrid-agent-os",
              label: "hybrid-agent-os",
              path: "/root/hybrid-agent-os",
            },
            {
              repo_id: "mcharness-public-export",
              label: "mcharness-public-export",
              path: "/root/mcharness-public-export",
            },
          ],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          configured: true,
          provider: "openrouter",
          model: "openrouter/auto",
          planning_enabled: true,
          notes: [],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/plan") && method === "POST") {
      captainLoopCtx.activePlan = captainPlanResponse;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(captainPlanResponse),
      });
      return;
    }

    if (pathname.endsWith("/sessions") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: runnerStatus.session_id }),
      });
      return;
    }

    if (pathname.endsWith("/queue") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ queue_item_id: "queue-captain-1" }),
      });
      return;
    }

    if (pathname.endsWith("/prompt-export") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    if (pathname.endsWith("/runner/start") && method === "POST") {
      runnerStartCalls.push(body);
      runnerStatus = { ...runnerStatus, status: "running" };
      captainLoopCtx.runnerStatus = runnerStatus;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-prompt") && method === "POST") {
      sendPromptCalls.push(body.prompt);
      transcriptText = `${transcriptText}\n${body.prompt}\nCaptain response pending.`;
      runnerStatus = { ...runnerStatus, status: "awaiting_response" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          injected: true,
          session_id: runnerStatus.session_id,
          status: runnerStatus.status,
          transcript_excerpt: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: runnerStatus.session_id,
          runner_id: runnerStatus.runner_id,
          lane_id: runnerStatus.lane_id,
          status: runnerStatus.status,
          transcript_path: "/tmp/captain-plan-transcript.txt",
          transcript: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/stop")) {
      runnerStatus = { ...runnerStatus, status: "stopped" };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...runnerStatus, stopped_at: new Date().toISOString() }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("http://127.0.0.1:8125/web/warden/index.html");
  await expect(page.locator("[data-testid='develop-plan-primary']")).toBeVisible();

  await page.locator("[data-testid='develop-plan-primary']").click();
  const captainModal = page.locator("#captain-deck-modal");
  await expect(captainModal).toBeVisible();
  await captainModal.locator("#captain-goal").fill("Build a webpage just like aol.com");
  await expect(captainModal.locator("#captain-create-plan")).toBeEnabled();
  await captainModal.locator("#captain-create-plan").click();
  await expect(captainModal.locator("[data-testid='captain-plan-status']")).toContainText("Plan ready: Build AOL-inspired webpage");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Build AOL-inspired webpage");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Inspect frontend structure");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Implement layout");
  await expect(captainModal.locator("[data-testid='captain-plan-body']")).toContainText("Verify and report");
  await expect(captainModal.locator("[data-testid='captain-deploy-first']")).toBeEnabled();
  await expect(captainModal.locator("[data-testid='captain-copy-plan']")).toBeEnabled();

  await page.evaluate(() => {
    const original = window.setTimeout;
    window.setTimeout = (fn, ms, ...args) => (ms === 10000 ? original(fn, 0, ...args) : original(fn, ms, ...args));
  });

  await captainModal.locator("[data-testid='captain-deploy-first']").click();
  await expect.poll(() => runnerStartCalls.length).toBe(1);
  await expect.poll(() => sendPromptCalls.length).toBe(1);
  await expect(sendPromptCalls[0]).toContain("Exact goal: Build a webpage just like aol.com");
  await expect(page.locator("#captain-deck-modal")).not.toBeVisible();

  const mon = page.locator("#live-cli-modal");
  await expect(mon).toBeVisible();
  await expect(page.locator("#modal-info")).toContainText("Repo: hybrid-agent-os");
  await expect(page.locator("#modal-info")).toContainText("Status: Running");
  await expect(page.locator("[data-testid='quick-reply-status']")).toContainText("Prompt sent to Codex.");
  await expect(mon.locator("[data-testid='modal-transcript']")).toContainText("Captain response pending.");
  await mon.locator("#modal-stop").click();
  await expect.poll(() => runnerStatus.status).toBe("stopped");
});

test("Captain supervised step loop advances manually in Mission", async ({ page }) => {
  let runnerStatus = {
    session_id: "captain-loop-session",
    runner_id: "run_captain_loop",
    lane_id: "codex_cli",
    repo_id: "hybrid-agent-os",
    status: "waiting_for_codex",
    tmux_session_name: "mch_captain_loop",
    attach_command: "tmux attach -t mch_captain_loop",
  };
  const sendPromptCalls = [];
  const captainLoopCtx = {
    activePlan: null,
    runnerStatus: null,
    dispatchCalls: [],
    completeCalls: [],
    reviseCalls: [],
    stopCalls: [],
  };
  const captainPlanResponse = normalizeMockCaptainPlan({
    ok: true,
    plan_id: "plan_loop_ui",
    title: "Captain Loop UI Plan",
    summary: "Supervised manual progression.",
    repo_id: "hybrid-agent-os",
    steps: [
      {
        id: "step_1",
        title: "Inspect frontend structure",
        agent: "codex_cli",
        prompt: "Inspect the frontend entrypoints only.",
        status: "queued",
      },
      {
        id: "step_2",
        title: "Implement layout",
        agent: "codex_cli",
        prompt: "Implement the requested layout change.",
        status: "queued",
      },
    ],
  });

  page.on("dialog", async (dialog) => {
    await dialog.accept("Inspect the frontend entrypoints and report only.");
  });

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;
    captainLoopCtx.runnerStatus = runnerStatus;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          public_write_enabled: true,
        }),
      });
      return;
    }

    if (await fulfillCaptainLoopRoute(route, captainLoopCtx)) {
      return;
    }

    if (await fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled: true })) {
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          repos: [
            { repo_id: "hybrid-agent-os", label: "hybrid-agent-os", path: "/root/hybrid-agent-os" },
          ],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, configured: true, planning_enabled: true, provider: "openrouter", model: "openrouter/auto" }),
      });
      return;
    }

    if (pathname.endsWith("/captain/plan") && method === "POST") {
      captainLoopCtx.activePlan = captainPlanResponse;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(captainPlanResponse),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-prompt") && method === "POST") {
      sendPromptCalls.push(body.prompt);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, injected: true, session_id: runnerStatus.session_id, status: "awaiting_response" }),
      });
      return;
    }

    if (pathname.endsWith("/runner/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: runnerStatus.session_id, transcript: "Captain loop transcript." }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("http://127.0.0.1:8125/web/warden/index.html");
  await page.locator("[data-testid='develop-plan-primary']").click();
  const captainModal = page.locator("#captain-deck-modal");
  await captainModal.locator("#captain-goal").fill("Prove supervised Captain loop in Mission.");
  await captainModal.locator("#captain-create-plan").click();
  await expect(captainModal.locator("[data-testid='captain-plan-status']")).toContainText("Plan ready: Captain Loop UI Plan");
  await captainModal.locator("[data-testid='captain-close']").click();
  await expect(captainModal).not.toBeVisible();
  await expect(page.locator("[data-testid='current-mission-plan']")).toBeVisible();
  await expect(page.locator("[data-testid='captain-plan-steps']")).toContainText("Inspect frontend structure");
  await expect(page.locator("[data-testid='captain-step-actions-step_1']")).toContainText("Deploy Current Step");

  await page.evaluate(() => {
    const original = window.setTimeout;
    window.setTimeout = (fn, ms, ...args) => (ms === 10000 ? original(fn, 0, ...args) : original(fn, ms, ...args));
  });

  await page.locator("[data-testid='captain-step-actions-step_1'] button:has-text('Mark Step Done')").click();
  await expect.poll(() => captainLoopCtx.completeCalls.length).toBe(1);
  expect(captainLoopCtx.dispatchCalls.length).toBe(0);
  await expect(page.locator("[data-testid='captain-step-actions-step_2']")).toContainText("Deploy Next Step");

  await page.locator("[data-testid='captain-step-actions-step_2'] button:has-text('Deploy Next Step')").click();
  await expect.poll(() => captainLoopCtx.dispatchCalls.length).toBe(1);
  await expect(page.locator("#live-cli-modal")).toBeVisible();
  await expect.poll(() => sendPromptCalls.length).toBe(1);

  await page.locator("#live-cli-modal #modal-close, #live-cli-modal .modal-close").first().click({ force: true }).catch(() => {});
  await page.evaluate(() => {
    const modal = document.getElementById("live-cli-modal");
    if (modal) modal.style.display = "none";
  });

  await page.locator("[data-testid='captain-step-actions-step_2'] button:has-text('Revise Step')").click();
  await expect.poll(() => captainLoopCtx.reviseCalls.length).toBe(1);
  await expect(page.locator("[data-testid='captain-plan-steps']")).toContainText("REVISED");

  await page.locator("[data-testid='captain-stop-plan']").click();
  await expect.poll(() => captainLoopCtx.stopCalls.length).toBe(1);
  await expect(page.locator("[data-testid='current-mission-empty']")).toBeVisible();
});

test("Agent Registry configure flow and Captain dropdown use registered agents", async ({ page }) => {
  let registeredAgents = [];
  const agentPostCalls = [];
  const testConfigCalls = [];

  await page.addInitScript(() => {
    window.__storageWrites = [];
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      window.__storageWrites.push([key, value]);
      return originalSetItem.call(this, key, value);
    };
  });

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          public_write_enabled: true,
        }),
      });
      return;
    }

    if (pathname.endsWith("/agent-lanes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          manual_mode: true,
          lanes: [{ lane_id: "codex_cli", title: "Codex CLI", installed: true }],
        }),
      });
      return;
    }

    if (pathname.endsWith("/agents/templates")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(agentRegistryTemplatesPayload()),
      });
      return;
    }

    if (pathname.endsWith("/agents") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          registry_write_enabled: true,
          agents: [builtinCodexAgent(), ...registeredAgents],
        }),
      });
      return;
    }

    if (pathname.endsWith("/agents/test-config") && method === "POST") {
      testConfigCalls.push(body);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          adapter: "jules_remote",
          status: "connected",
          message: "Jules API key verified via sources list.",
          safe_details: { sources_count: 1 },
        }),
      });
      return;
    }

    if (pathname.endsWith("/agents") && method === "POST") {
      agentPostCalls.push(body);
      const created = {
        id: "jules_remote_test01",
        name: body.name,
        kind: body.kind,
        adapter: body.adapter,
        enabled: body.enabled,
        builtin: false,
        user_created: true,
        status: "ready",
        connection_status: "connected",
        configured: true,
        runnable: false,
        description: "Jules profile only.",
        capabilities: ["remote_planning", "status_tracking"],
      };
      registeredAgents = [created];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, agent: created }),
      });
      return;
    }

    if (pathname.match(/\/agents\/[^/]+$/) && method === "DELETE") {
      registeredAgents = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, deleted_id: pathname.split("/").pop() }),
      });
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          repos: [{ repo_id: "mcharness-public-export", label: "mcharness-public-export", path: "/root/mcharness-public-export" }],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          configured: true,
          provider: "openrouter",
          model: "openrouter/auto",
          planning_enabled: true,
          key_source: "env",
          private_key_setup_enabled: true,
          notes: [],
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("/web/warden/index.html");
  await expect(page.locator("h1")).toContainText("Warden");
  await expect(page.locator("[data-testid='nav-mission']")).toHaveClass(/active/);
  await page.locator("[data-testid='nav-agents']").click();
  await expect(page.locator("text=Agent Library")).toBeVisible();
  await expect(page.locator("[data-testid='agent-group-ready']")).toContainText("Ready to Run");
  await expect(page.locator("#codex-card")).toContainText("Codex CLI");
  await expect(page.getByRole("button", { name: "Add Agent" })).toBeVisible();
  await expect(page.locator("input[type='text'][placeholder*='shell'], textarea[placeholder*='shell']")).toHaveCount(0);

  await page.getByRole("button", { name: "Add Agent" }).click();
  const addModal = page.locator("#add-agent-modal");
  await expect(addModal).toBeVisible();
  await expect(addModal.locator("[data-testid='add-agent-step-choose']")).toBeVisible();
  await expect(addModal.locator("button[data-template-adapter='jules_remote']")).toBeVisible();
  await expect(addModal.locator("button[data-template-adapter='custom_cli']")).toBeDisabled();

  await addModal.locator("button[data-template-adapter='jules_remote']").click();
  await expect(addModal.locator("[data-testid='add-agent-step-config']")).toBeVisible();
  await expect(addModal.locator("[data-testid='add-agent-api-key']")).toHaveAttribute("type", "password");
  await expect(addModal.locator("[data-testid='add-agent-test']")).toBeVisible();
  await expect(addModal.locator("[data-testid='add-agent-save']")).toBeDisabled();

  await addModal.locator("[data-testid='add-agent-name']").fill("Jules Remote Worker");
  await addModal.locator("[data-testid='add-agent-api-key']").fill("test-jules-key");
  await addModal.locator("[data-testid='add-agent-test']").click();
  await expect.poll(() => testConfigCalls.length).toBe(1);
  await expect(testConfigCalls[0].adapter).toBe("jules_remote");
  await expect(testConfigCalls[0].api_key).toBe("test-jules-key");
  await expect(addModal.locator("[data-testid='add-agent-test-status']")).toContainText("Jules API key verified");
  await expect(addModal.locator("[data-testid='add-agent-save']")).toBeEnabled();

  await addModal.locator("[data-testid='add-agent-save']").click();
  await expect.poll(() => agentPostCalls.length).toBe(1);
  await expect(agentPostCalls[0].adapter).toBe("jules_remote");
  await expect(agentPostCalls[0].api_key).toBe("test-jules-key");
  await expect(addModal.locator("[data-testid='add-agent-api-key']")).toHaveValue("");
  await expect(page.locator("[data-testid='agent-group-connected']")).toBeVisible();
  await expect(page.locator("[data-testid='agent-group-connected']")).toContainText("Connected / Setup Complete");
  await expect(page.locator(".registered-agent-card")).toContainText("Jules Remote Worker");
  await expect(page.locator(".registered-agent-card")).toContainText("Connected for planning and status. Remote execution comes next.");
  await expect(page.locator(".registered-agent-card button", { hasText: "Use Agent" })).toHaveCount(0);
  await expect(page.locator(".registered-agent-card button", { hasText: "Edit Config" })).toBeVisible();
  const julesView = page.locator(".registered-agent-card [data-testid='view-agent-jules']");
  await expect(julesView).toBeVisible();
  await expect(julesView).toHaveAttribute("href", "https://jules.google.com/session");
  await expect(julesView).toHaveAttribute("target", "_blank");
  await expect(julesView).toHaveAttribute("rel", "noopener noreferrer");
  await expect(julesView).toHaveAttribute("title", "Open Jules remote agent workspace");
  await expect(page.evaluate(() => window.__storageWrites || [])).resolves.toEqual([]);

  await page.locator("[data-testid='develop-plan-primary']").click();
  const captainModal = page.locator("#captain-deck-modal");
  await expect(captainModal).toBeVisible();
  await expect(captainModal.locator("[data-testid='captain-agent-select']")).toContainText("Codex CLI — Ready");
  await expect(captainModal.locator("[data-testid='captain-agent-select']")).toContainText("Jules Remote Worker — Connected, execution coming next");
  await captainModal.locator("[data-testid='captain-agent-select']").selectOption("jules_remote_test01");
  await expect(captainModal.locator("[data-testid='captain-agent-note']")).toContainText("Jules Remote is configured for planning/status only. Execution comes next.");
  await expect(captainModal.locator("[data-testid='captain-create-plan']")).toBeDisabled();
  await expect(captainModal.locator("[data-testid='captain-deploy-first']")).toBeDisabled();
  await captainModal.locator("[data-testid='captain-agent-select']").selectOption("codex_cli");
  await expect(captainModal.locator("[data-testid='captain-agent-note']")).toBeHidden();
});

test("run history and evidence appear after private Codex dispatch", async ({ page }) => {
  const runs = [];
  const evidence = [];
  let transcriptText = "Codex output line 1\nCodex output line 2\n";
  let runnerStatus = {
    session_id: "history-session",
    runner_id: "run_history01",
    lane_id: "codex_cli",
    repo_id: "mcharness-public-export",
    status: "running",
    tmux_session_name: "mch_history",
    attach_command: "tmux attach -t mch_history",
  };

  await page.route("**/api/mcharness/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    const body = route.request().postDataJSON ? route.request().postDataJSON() : null;

    if (pathname.endsWith("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          service: "mcharness-control-plane",
          commit: "test-commit",
          mode: "public_manual",
          real_agent_launch_enabled: false,
          arbitrary_command_execution_enabled: false,
          public_write_enabled: true,
          tmux_runner_enabled: true,
          codex_runner_enabled: true,
          available_lanes_count: 7,
          repo_count: 1,
          manual_mode: true,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runs/recent")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ service: "mcharness-control-plane", service_mode: "private", runs }),
      });
      return;
    }

    if (pathname.match(/\/runs\/[^/]+$/) && method === "GET") {
      const runId = pathname.split("/").pop();
      const run = runs.find((item) => item.run_id === runId);
      if (!run) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Run not found" }) });
        return;
      }
      const linked = evidence.filter((item) => item.run_id === runId);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ service: "mcharness-control-plane", service_mode: "private", run, evidence: linked }),
      });
      return;
    }

    if (pathname.endsWith("/evidence/recent")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ service: "mcharness-control-plane", service_mode: "private", evidence }),
      });
      return;
    }

    if (pathname.match(/\/evidence\/[^/]+$/) && method === "GET") {
      const evidenceId = pathname.split("/").pop();
      const item = evidence.find((entry) => entry.evidence_id === evidenceId);
      if (!item) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Evidence not found" }) });
        return;
      }
      const linkedRun = runs.find((run) => run.run_id === item.run_id);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          service_mode: "private",
          evidence: { ...item, content: item.content_excerpt },
          linked_run: linkedRun ? { run_id: linkedRun.run_id, title: linkedRun.title, status: linkedRun.status } : null,
        }),
      });
      return;
    }

    if (pathname.endsWith("/agent-lanes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          manual_mode: true,
          lanes: [{ lane_id: "codex_cli", title: "Codex CLI", installed: true, runner_mode: "controlled_run_ready" }],
        }),
      });
      return;
    }

    if (await fulfillAgentRegistryRoute(route, { method, pathname, registryWriteEnabled: true })) {
      return;
    }

    if (pathname.endsWith("/repos")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          service: "mcharness-control-plane",
          repos: [{ repo_id: "mcharness-public-export", label: "mcharness-public-export", path: "/root/mcharness-public-export" }],
        }),
      });
      return;
    }

    if (pathname.endsWith("/captain/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          configured: true,
          provider: "openrouter",
          model: "openrouter/auto",
          planning_enabled: true,
          key_source: "env",
          private_key_setup_enabled: true,
          notes: [],
        }),
      });
      return;
    }

    if (pathname.endsWith("/sessions") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: "history-session" }),
      });
      return;
    }

    if (pathname.endsWith("/queue") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ queue_item_id: "queue-history-1" }),
      });
      return;
    }

    if (pathname.endsWith("/prompt-export") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ prompt_text: "History prompt export" }),
      });
      return;
    }

    if (pathname.endsWith("/runner/start") && method === "POST") {
      const run = {
        run_id: runnerStatus.runner_id,
        title: body.title || "History smoke",
        agent_id: "codex_cli",
        agent_adapter: "codex_cli",
        repo_id: "mcharness-public-export",
        status: "dispatched",
        started_at: "2026-06-09T12:00:00.000Z",
        prompt_excerpt: body.prompt || "History prompt",
        transcript_excerpt: "",
        evidence_count: 0,
        evidence_ids: [],
      };
      runs.unshift(run);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...runnerStatus,
          warden_run: run,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/send-prompt") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, status: "running", transcript_excerpt: transcriptText }),
      });
      return;
    }

    if (pathname.endsWith("/runner/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(runnerStatus),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "history-session",
          runner_id: runnerStatus.runner_id,
          transcript: transcriptText,
        }),
      });
      return;
    }

    if (pathname.endsWith("/runner/transcript-to-evidence") && method === "POST") {
      const item = {
        evidence_id: "ev_history01",
        run_id: runnerStatus.runner_id,
        type: "transcript",
        title: "Codex transcript snapshot",
        summary: "Saved runner transcript as evidence",
        content_excerpt: transcriptText,
        created_at: "2026-06-09T12:05:00.000Z",
        agent_id: "codex_cli",
        source: "live_monitor",
        redacted: false,
      };
      evidence.unshift(item);
      const run = runs.find((entry) => entry.run_id === runnerStatus.runner_id);
      if (run) {
        run.evidence_count = 1;
        run.evidence_ids = [item.evidence_id];
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, warden_evidence: item }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled route: ${pathname}` }) });
  });

  await page.goto("/web/warden/index.html");
  await page.locator("[data-testid='nav-runs']").click();
  await expect(page.locator("[data-testid='runs-empty-state']")).toBeVisible();

  await page.locator("[data-testid='nav-agents']").click();
  await page.getByRole("button", { name: "Use Agent" }).click();
  const useModal = page.locator("#use-agent-modal");
  await useModal.locator("#modal-task-title").fill("History smoke");
  await useModal.locator("#modal-prompt").fill("Capture run history after dispatch.");
  await useModal.locator("#deploy-prompt-btn").click();

  const liveModal = page.locator("#live-cli-modal");
  await expect(liveModal).toBeVisible();
  await liveModal.locator("[data-testid='modal-close']").click();
  await expect(liveModal).not.toBeVisible();
  await page.locator("[data-testid='nav-runs']").click();
  await expect(page.locator("[data-testid='runs-list']")).toBeVisible();
  await expect(page.locator("[data-testid='runs-list']")).toContainText("History smoke");
  await expect(page.locator("[data-testid='runs-list']")).toContainText("codex_cli");
  await page.locator("[data-testid='runs-list'] button", { hasText: "View Run" }).click();
  const runModal = page.locator("#run-detail-modal");
  await expect(runModal).toBeVisible();
  await expect(runModal.locator("[data-testid='run-detail-prompt']")).toContainText("Capture run history");
  await runModal.locator("[data-testid='run-detail-close']").click();

  await page.locator("[data-testid='nav-agents']").click();
  await page.locator("[data-testid='view-agent-codex']").click();
  await page.locator("[data-testid='modal-save-evidence']").click();
  await expect(page.locator("[data-testid='quick-reply-status']")).toContainText("Transcript saved as evidence");
  await liveModal.locator("[data-testid='modal-close']").click();
  await expect(liveModal).not.toBeVisible();

  await page.locator("[data-testid='nav-evidence']").click();
  await expect(page.locator("[data-testid='evidence-list']")).toBeVisible();
  await expect(page.locator("[data-testid='evidence-list']")).toContainText("Codex transcript snapshot");
  await page.locator("[data-testid='evidence-list'] button", { hasText: "View Evidence" }).click();
  const evidenceModal = page.locator("#evidence-detail-modal");
  await expect(evidenceModal).toBeVisible();
  await expect(evidenceModal.locator("[data-testid='evidence-detail-content']")).toContainText("Codex output line 1");
  await expect(page.locator("text=sk-or-")).toHaveCount(0);
});
