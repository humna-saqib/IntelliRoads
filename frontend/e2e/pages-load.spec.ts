import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

const ROUTES_TO_TEST = [
  { path: '/', expectedText: /Overview/i },
  { path: '/details', expectedText: /Detailed/i },
  { path: '/map', expectedText: /Map|Corridor|Intersection/i },
  { path: '/analytics', expectedText: /Analytics|Performance/i },
  { path: '/alerts', expectedText: /Past warnings|Alerts|Warnings/i },
  { path: '/reports', expectedText: /Reports/i },
  { path: '/settings', expectedText: /Settings/i },
];

test.describe('Every page loads without a blank screen', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true });
  });

  for (const { path, expectedText } of ROUTES_TO_TEST) {
    test(`route "${path}" renders content without a blank page`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'domcontentloaded' });

      // Verify that main container exists and has content
      const main = page.locator('main');
      await expect(main).toBeVisible({ timeout: 10_000 });

      // Verify text matching expected section or header
      await expect(page.locator('body')).toContainText(expectedText, { timeout: 10_000 });

      // Make sure body is not blank/empty
      const innerText = await main.innerText();
      expect(innerText.trim().length).toBeGreaterThan(10);
    });
  }
});
