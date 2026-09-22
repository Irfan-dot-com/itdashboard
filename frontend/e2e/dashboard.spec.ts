import { expect, test } from '@playwright/test';

test.describe('IT Dashboard', () => {
  test('loads the estate view and shows KPI strip', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Estate' })).toBeVisible();
    await expect(page.getByText('Estate health')).toBeVisible();
    await expect(page.getByText('Open P1')).toBeVisible();
  });

  test('navigates to alerts view from sidebar', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /^Alerts/ }).click();
    await expect(page).toHaveURL(/\/alerts$/);
    await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible();
  });

  test('toggles simulation', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByRole('button', { name: /Toggle live simulation/i });
    await toggle.click();
    await expect(toggle).toContainText('Live');
  });
});
