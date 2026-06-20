const PLAYWRIGHT_TEST_MODULE =
  process.env.MCHARNESS_PLAYWRIGHT_TEST_MODULE || "/root/.hermes/node/lib/node_modules/playwright/test";
const { defineConfig } = require(PLAYWRIGHT_TEST_MODULE);

const webServer =
  process.env.MCHARNESS_PLAYWRIGHT_START_SERVER === "1"
    ? {
        command: "python -m uvicorn src.server.api:app --host 127.0.0.1 --port 8124",
        url: "http://127.0.0.1:8124/web/warden/index.html",
        reuseExistingServer: true,
        stdout: "pipe",
        stderr: "pipe",
        timeout: 60_000,
      }
    : undefined;

module.exports = defineConfig({
  testDir: "./tests/browser",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results/playwright",
  use: {
    baseURL: "http://127.0.0.1:8124",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 1200 },
    trace: "on",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer,
});
