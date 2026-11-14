import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('Playwright Setup & Route Interception', () => {
  test('loads overview with intercepted mock API without backend', async ({ page }) => {
    await setupApiMocks(page, { authenticated: true });
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveTitle(/IntelliRoads/i);
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible({ timeout: 15_000 });
  });
});
