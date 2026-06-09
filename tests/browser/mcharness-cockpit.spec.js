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
  await page.goto("/web/mctable-studio/cockpit-app.html");

  // Simple default UI
  await expect(page.locator("h1")).toContainText("McHarness");
  await expect(page.locator("text=Agent Library")).toBeVisible();
  await expect(page.getByRole("button", { name: "Develop Plan" })).toBeVisible();
  await expect(page.locator("#codex-card")).toBeVisible();
  await expect(page.locator('#codex-card')).toContainText('Codex CLI');
  await expect(page.locator("text=Add Agent — Coming Soon")).toBeVisible();

  await page.getByRole("button", { name: "Develop Plan" }).click();
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

  // Close use modal if still open
  const cancel = useModal.locator("#cancel-use-agent");
  if (await cancel.isVisible()) await cancel.click();

  // Live monitor should have been opened by the deploy flow; verify it shows disabled/read-only
  const mon = page.locator("#live-cli-modal").or(page.getByTestId("live-cli-modal"));
  await expect(mon).toBeVisible({ timeout: 5000 });
  await expect(mon).toContainText("Live read-only view. Use the buttons below for safe replies.");

  // Close
  await mon.locator("#modal-close").or(page.getByTestId("modal-close")).click();
  await expect(mon).not.toBeVisible();

  // Legacy link exists for advanced
  await expect(page.locator("#legacy-link")).toBeVisible();

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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          plan_id: "plan_saved_key",
          title: "Captain Saved Key Plan",
          summary: "Plan after saved key setup.",
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
        }),
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

  await page.goto("http://127.0.0.1:8125/web/mctable-studio/cockpit-app.html");
  await expect(page.getByRole("button", { name: "Develop Plan" })).toBeVisible();

  await page.getByRole("button", { name: "Develop Plan" }).click();
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
      sendKeyCalls.push(body.key);
      runnerStatus = { ...runnerStatus, status: "prompt_sent" };
      transcriptText = `${transcriptText}\n# [quick reply ${body.key}]\nSent: ${body.key}\n`;
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

  await page.goto("http://127.0.0.1:8125/web/mctable-studio/cockpit-app.html");
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
  const captainPlanResponse = {
    ok: true,
    plan_id: "plan_1234",
    title: "Build AOL-inspired webpage",
    summary: "Create an AOL-inspired homepage layout in the existing frontend.",
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
          repo_count: 2,
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

  await page.goto("http://127.0.0.1:8125/web/mctable-studio/cockpit-app.html");
  await expect(page.getByRole("button", { name: "Develop Plan" })).toBeVisible();

  await page.getByRole("button", { name: "Develop Plan" }).click();
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
  await expect(page.locator("#captain-deck-modal")).not.toBeVisible();

  const mon = page.locator("#live-cli-modal");
  await expect(mon).toBeVisible();
  await expect(page.locator("#modal-info")).toContainText("Repo: hybrid-agent-os");
  await expect(page.locator("#modal-info")).toContainText("Status: Running");
  await expect(mon.locator("[data-testid='modal-transcript']")).toContainText("Captain response pending.");
  await mon.locator("#modal-stop").click();
  await expect.poll(() => runnerStatus.status).toBe("stopped");
});
