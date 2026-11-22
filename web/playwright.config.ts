import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8010;
const WEB_PORT = 3010;
const E2E_DB = "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid_e2e";
const apiEnv = {
  DATABASE_URL: E2E_DB,
  DRAFTER: "template",
  WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
  OPENROUTER_API_KEY: "",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run python -m getpaid.e2e_reset && uv run uvicorn getpaid.asgi:app --port ${API_PORT}`,
      cwd: "../api",
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: apiEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
