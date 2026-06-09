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
  await page.goto("/web/mctable-studio/cockpit-app.html");

  // Simple default UI
  await expect(page.locator("h1")).toContainText("McHarness");
  await expect(page.locator("text=Agent Library")).toBeVisible();
  await expect(page.locator("#codex-card")).toBeVisible();
  await expect(page.locator('#codex-card')).toContainText('Codex CLI');
  await expect(page.locator("text=Add Agent — Coming Soon")).toBeVisible();

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
  await expect(mon).toContainText("Read-only monitor");
  await expect(mon).toContainText("No arbitrary shell input");

  // Close
  await mon.locator("#modal-close").or(page.getByTestId("modal-close")).click();
  await expect(mon).not.toBeVisible();

  // Legacy link exists for advanced
  await expect(page.locator("#legacy-link")).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("cockpit-final.png"), fullPage: true });
});

test("private runner quick replies send allowed keys and refresh transcript", async ({ page }) => {
  let transcriptText = [
    "Codex update available",
    "",
    "1. Update now",
    "2. Skip",
    "3. Skip until next version",
    "",
    "Press enter to continue",
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
  await expect(mon.locator("[data-testid='quick-reply-panel']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='1']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='2']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='3']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Enter']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Esc']")).toBeVisible();
  await expect(mon.locator("[data-quick-reply='Ctrl+C']")).toBeVisible();
  await expect(mon.locator("input, textarea")).toHaveCount(0);

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
