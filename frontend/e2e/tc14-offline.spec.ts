import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-14: Backend stopped displays friendly offline message', () => {
  test('home page shows friendly offline error state and retry button when backend fails', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    // simulateOffline aborts all /api/ network requests
    await setupApiMocks(page, { authenticated: true, simulateOffline: true });

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Should NOT be a blank screen
    const body = page.locator('body');
    await expect(body).toBeVisible({ timeout: 10_000 });

    // Should display friendly offline message
    const errorHeading = page.locator('text=/Traffic system offline|Live traffic system is offline/i');
    await expect(errorHeading).toBeVisible({ timeout: 10_000 });

    // Should offer a retry button
    const retryBtn = page.getByRole('button', { name: /Try again|Retry/i });
    await expect(retryBtn).toBeVisible({ timeout: 5_000 });
  });

  test('details page shows friendly offline error state when backend is stopped', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true, simulateOffline: true });

    await page.goto('/details', { waitUntil: 'domcontentloaded' });

    // Should NOT be a blank screen
    const body = page.locator('body');
    await expect(body).toBeVisible({ timeout: 10_000 });

    // Should display offline error state
    const errorHeading = page.locator('text=/Live traffic system is offline|Traffic system offline/i');
    await expect(errorHeading).toBeVisible({ timeout: 10_000 });

    // Should offer a retry button
    const retryBtn = page.getByRole('button', { name: /Try again|Retry/i });
    await expect(retryBtn).toBeVisible({ timeout: 5_000 });
  });
});
