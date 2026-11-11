import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-03: First-visit tour opens once and does not return after Skip', () => {
  test('tour appears on first visit and does not reappear after skipping', async ({ page }) => {
    // Make sure the tour flag is cleared (first visit)
    await page.addInitScript(() => {
      localStorage.removeItem('intelliroads_tour_completed');
    });
    await setupApiMocks(page, { authenticated: true });

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Tour modal should be visible with "Welcome to IntelliRoads"
    const tourDialog = page.locator('[aria-label="First-visit guided tour"]');
    await expect(tourDialog).toBeVisible({ timeout: 10_000 });
    await expect(tourDialog).toContainText('Welcome to IntelliRoads');

    // Click "Skip tour"
    await page.click('[aria-label="Skip tour"]');

    // Tour should be dismissed
    await expect(tourDialog).not.toBeVisible({ timeout: 5_000 });

    // localStorage flag should be set
    const flag = await page.evaluate(() => localStorage.getItem('intelliroads_tour_completed'));
    expect(flag).toBe('true');

    // Reload the page — tour should NOT reappear
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(tourDialog).not.toBeVisible({ timeout: 10_000 });
  });
});

