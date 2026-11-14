import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-06: Switching Standard timing <-> Smart AI', () => {
  test('switching between Standard timing and Smart AI changes mode with no error', async ({ page }) => {
    // Start with RULE_BASED mode, tour completed
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true, controllerMode: 'RULE_BASED' });

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Locate the radio buttons in TimingModeSwitch
    const standardBtn = page.getByRole('radio', { name: /Standard timing/i });
    const smartAiBtn = page.getByRole('radio', { name: /Smart AI/i });

    // Verify initial state is Standard timing (RULE_BASED)
    await expect(standardBtn).toBeVisible({ timeout: 10_000 });
    await expect(standardBtn).toHaveAttribute('aria-checked', 'true');
    await expect(smartAiBtn).toHaveAttribute('aria-checked', 'false');

    // Switch to Smart AI
    await smartAiBtn.click();

    // Verify Smart AI is now checked
    await expect(smartAiBtn).toHaveAttribute('aria-checked', 'true', { timeout: 5_000 });
    await expect(standardBtn).toHaveAttribute('aria-checked', 'false');

    // Toast or status text update
    await expect(page.locator('text=Smart AI is adapting green lights to live queues')).toBeVisible({ timeout: 5_000 });

    // Switch back to Standard timing
    await standardBtn.click();

    // Verify Standard timing is checked again
    await expect(standardBtn).toHaveAttribute('aria-checked', 'true', { timeout: 5_000 });
    await expect(smartAiBtn).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('text=Standard timing is cycling through fixed schedules')).toBeVisible({ timeout: 5_000 });
  });
});
