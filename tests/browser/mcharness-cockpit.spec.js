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

test("proves the full manual-compatible cockpit operator loop in the browser", async ({ page }, testInfo) => {
  const sessionTitle = "Browser Proof Session";
  const sessionObjective = "Prove the manual-compatible control-plane loop in a real browser.";
  const planInstruction = "Create a bounded prompt, capture a manual transcript, and persist artifacts.";
  const queuedPromptTitle = "Browser Proof Extra Prompt";
  const queuedPromptText = "Inspect the current repo state, summarize the lane handoff, and return transcript evidence.";
  const queuedPromptEvidence = "Transcript pasted back.\nArtifacts captured.";
  const queuedPromptChecks = "Prompt export contains safety constraints.\nFinal proof format stays explicit.";
  const gateRejectNote = "Reject once for browser proof.";
  const gateMoreEvidenceNote = "Need more evidence for browser proof.";
  const gateApproveNote = "Approved after browser proof.";

  await page.goto("/web/mctable-studio/cockpit-app.html");

  for (const label of [
    "SERVER CONTROL PLANE",
    "ALLOWLISTED CLI LANES ONLY",
    "ARBITRARY COMMAND EXECUTION DISABLED",
    "PUBLIC REAL AGENT LAUNCH DISABLED",
    "FAKE/MANUAL MODE",
  ]) {
    await expect(page.locator(".banner", { hasText: label }).first()).toBeVisible();
  }

  await page.getByLabel("Repo / worktree").selectOption("/root/mcharness-public-export");
  await page.getByLabel("CLI agent lane").selectOption("manual_paste");
  await page.locator("#session-title").fill(sessionTitle);
  await page.locator("#session-objective").fill(sessionObjective);
  await page.locator("#session-plan").fill(planInstruction);
  await page.getByRole("button", { name: "New Session" }).click();

  await expect(page.getByTestId("session-card")).toContainText(sessionTitle);
  await expect(page.locator("#session-summary")).toContainText(sessionObjective);
  await expect(page.locator("#session-summary")).toContainText("/root/mcharness-public-export");
  await expect(page.locator("#session-summary")).toContainText("manual_paste");

  await page.locator("#queue-title").fill(queuedPromptTitle);
  await page.locator("#queue-prompt").fill(queuedPromptText);
  await page.locator("#queue-file-scope").fill("web/mctable-studio/cockpit-app.js\nsrc/marius_desktop/api.py");
  await page.locator("#queue-acceptance").fill(queuedPromptChecks);
  await page.locator("#queue-evidence").fill(queuedPromptEvidence);
  await page.getByRole("button", { name: "Queue Prompt" }).click();

  const queuedPromptCard = page.getByTestId("queue-item").filter({ hasText: queuedPromptTitle });
  await expect(queuedPromptCard).toBeVisible();
  await queuedPromptCard.click();
  await expect(page.locator("#preview-title")).toContainText(queuedPromptTitle);
  await page.getByRole("button", { name: "Load Preview" }).click();

  const preview = page.locator("#prompt-preview");
  await expect(preview).toHaveValue(/# McHarness Bounded Minion Prompt/);
  await expect(preview).toHaveValue(new RegExp(`- Session title: ${sessionTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  await expect(preview).toHaveValue(/- Session id:/);
  await expect(preview).toHaveValue(/- Queue item id:/);
  await expect(preview).toHaveValue(new RegExp(`- Exact goal: ${sessionObjective.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  await expect(preview).toHaveValue(/## Safety constraints/);
  await expect(preview).toHaveValue(/## Acceptance tests/);
  await expect(preview).toHaveValue(/## Required final proof format/);

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download .md" }).click(),
  ]);
  expect(download.suggestedFilename()).toContain(".md");
  await download.saveAs(testInfo.outputPath("queued-prompt.md"));

  await page.getByRole("button", { name: "Mark Exported" }).click();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "prompt_export" })).toBeVisible();

  await page.getByLabel("Evidence summary").fill("Browser proof manual transcript captured.");
  await page.getByLabel("Pasted transcript / worker result").fill("Transcript line 1\nTranscript line 2");
  await page.getByLabel("Git status").fill(" M web/mctable-studio/cockpit-app.js");
  await page.getByLabel("Git diff summary").fill(" web/mctable-studio/cockpit-app.js | 10 ++++++----");
  await page.getByLabel("Test output").fill("browser proof placeholder test output");
  await page.getByRole("button", { name: "Complete Assignment" }).click();

  await expect(page.getByTestId("artifact-card").filter({ hasText: "manual_result" })).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "evidence" })).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "git_status" }).first()).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "git_diff_summary" }).first()).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "test_output" }).first()).toBeVisible();
  await expect(page.getByTestId("evidence-card").first()).toContainText("Browser proof manual transcript captured.");

  await page.getByLabel("Gate reason / reviewer note").fill(gateRejectNote);
  await page.getByRole("button", { name: "Reject Gate" }).click();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "gate_decision" }).first()).toContainText(gateRejectNote);
  await expect(page.getByTestId("activity-item").first()).toContainText("Gate rejected");

  await page.getByLabel("Gate reason / reviewer note").fill(gateMoreEvidenceNote);
  await page.getByRole("button", { name: "Request More Evidence" }).click();
  await expect(page.getByTestId("artifact-card").filter({ hasText: gateMoreEvidenceNote }).first()).toBeVisible();

  await page.getByLabel("Gate reason / reviewer note").fill(gateApproveNote);
  await page.getByRole("button", { name: "Approve Gate" }).click();
  await expect(page.getByTestId("artifact-card").filter({ hasText: gateApproveNote }).first()).toBeVisible();

  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByTestId("activity-item").first()).toContainText("Session paused");

  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByTestId("activity-item").first()).toContainText("Continuation requested");

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByTestId("activity-item").first()).toContainText("Session stopped");

  await page.reload();
  await expect(page.locator("#session-summary")).toContainText(sessionTitle);
  await expect(page.getByTestId("session-card")).toContainText(sessionTitle);
  await expect(page.getByTestId("queue-item").filter({ hasText: queuedPromptTitle })).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: "manual_result" })).toBeVisible();
  await expect(page.getByTestId("artifact-card").filter({ hasText: gateApproveNote }).first()).toBeVisible();
  await expect(page.getByTestId("evidence-card").first()).toContainText("Browser proof manual transcript captured.");
  await expect(page.locator("#activity-log")).toContainText("Prompt marked sent");
  await expect(page.locator("#activity-log")).toContainText("Gate approved");
  await expect(page.locator("#activity-log")).toContainText("Session stopped");

  // runner foundation UI presence (controls added; actual start uses test-only fake lane + env in unit tests)
  await expect(page.locator('#runner-controls')).toBeVisible();
  await expect(page.getByTestId('runner-start-btn')).toBeVisible();
  await expect(page.getByTestId('runner-status-btn')).toBeVisible();
  await expect(page.getByTestId('runner-transcript-btn')).toBeVisible();
  await expect(page.getByTestId('runner-evidence-btn')).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath("cockpit-final.png"), fullPage: true });
});
