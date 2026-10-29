import { chromium } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const component = fileURLToPath(new URL("../", import.meta.url));
const token = readFileSync(
  component + ".local/isolation-test.token",
  "utf8",
).trim();
const query = readFileSync(
  component + ".local/browser-query.txt",
  "utf8",
).trim();
mkdirSync(component + "evidence", { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1100 },
  recordVideo: {
    dir: component + ".local/videos",
    size: { width: 1440, height: 1100 },
  },
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
try {
  await page.goto("http://127.0.0.1:8085");
  await page.getByLabel("Access token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByText("Private shopping session").waitFor();
  await page
    .getByRole("textbox", { name: "Search catalog", exact: true })
    .fill(query);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".product").first().waitFor();
  page.on("dialog", (dialog) => dialog.accept());
  await page.locator(".product button:not([disabled])").first().click();
  await page.locator(".line").first().waitFor();
  await page.screenshot({
    path: component + "evidence/storefront-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Continue to Shopify ↗" }).click();
  await page
    .getByRole("link", { name: "Open secure Shopify checkout ↗" })
    .waitFor();
  await page
    .getByRole("button", { name: "Remove", exact: true })
    .first()
    .click();
  await page.getByText("Your cart is empty.", { exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: component + "evidence/storefront-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Connect", exact: true }).waitFor();
  if ((await page.getByLabel("Access token").inputValue()) !== "")
    throw Error("Token retained after logout");
  if (errors.length) throw Error("Browser script errors");
  writeFileSync(
    component + "evidence/browser-check.json",
    JSON.stringify(
      {
        status: "PASSED",
        catalog_rendered: true,
        confirmed_add: true,
        checkout_link_received: true,
        item_removed: true,
        signout_clears_token: true,
        mobile_width: 390,
        page_errors: errors,
        checked_at: new Date().toISOString(),
      },
      null,
      2,
    ) + "\n",
  );
  console.log(
    "Browser checks passed; desktop/mobile screenshots saved. Private video remains in .local/videos.",
  );
} finally {
  await context.close();
  writeFileSync(
    component + ".local/browser-video.txt",
    await page.video().path(),
  );
  await browser.close();
}
