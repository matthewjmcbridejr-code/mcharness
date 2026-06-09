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
