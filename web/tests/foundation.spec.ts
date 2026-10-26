import { test, expect } from '@playwright/test';

test('real API readiness and all five application routes', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Five workflows. Verifiable results.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'BLOCKED', exact: true })).toBeVisible();
  await expect(page.getByText('GOOGLE_API_KEY', { exact: true })).toBeVisible();
  await expect(page.locator('.card')).toHaveCount(5);
  for (const id of ['lead_research', 'gemini_cli_tool', 'bug_assistant', 'code_reviewer', 'ecommerce']) {
    await page.locator(`nav a[href="#${id}"]`).click();
    await expect(page.getByRole('button', { name: 'Create session' })).toBeDisabled();
    await expect(page.getByText('This agent has not started.', { exact: false })).toBeVisible();
  }
  await page.goto('/');
  await page.screenshot({ path: '../docs/evidence/foundation-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '../docs/evidence/foundation-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
