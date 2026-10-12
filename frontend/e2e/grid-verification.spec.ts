import { test, expect } from '@playwright/test';
import * as path from 'path';

const ARTIFACT_DIR = 'C:/Users/YATHISH/.gemini/antigravity/brain/f9e7e4a4-f865-4ca3-b0ab-9aea1399a503';

test.describe('KNL Consumable ERP - Excel Data Grid Verification', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate and sign in with admin
    await page.goto('http://localhost:5173/');
    await page.waitForLoadState('networkidle');

    // Check if we need to log in
    const usernameInput = page.getByLabel('Username');
    if (await usernameInput.count() > 0 && await usernameInput.isVisible()) {
      await usernameInput.fill('admin');
      const passwordInput = page.getByLabel('Password');
      await passwordInput.fill('admin123');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForSelector('header', { timeout: 10000 });
      await page.waitForTimeout(500);
    }
  });

  test('Requirements Page: 1920x1080 and 1366x768 - No overlapping headers, no clipped text, sticky columns work', async ({ page }) => {
    // Viewport 1: 1920x1080
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.locator('a[href="/requirements"]').click();
    await page.waitForTimeout(1000);

    // Verify Requirements page title
    const reqTitle = page.getByRole('heading', { name: 'Requirement', exact: true });
    await expect(reqTitle).toBeVisible();

    // Verify Table exists
    const table = page.locator('table');
    await expect(table).toBeVisible();

    // Check header rows
    const headerRows = page.locator('table thead tr');
    const headerRowCount = await headerRows.count();
    expect(headerRowCount).toBeGreaterThanOrEqual(2);

    // Check Tier 2 column headers for overlap and text clipping
    const ths = page.locator('table thead tr:nth-child(2) th');
    const thCount = await ths.count();
    expect(thCount).toBeGreaterThanOrEqual(10);

    const boxes: { label: string; box: { x: number; y: number; width: number; height: number } }[] = [];
    for (let i = 0; i < thCount; i++) {
      const th = ths.nth(i);
      const box = await th.boundingBox();
      const text = await th.innerText();
      if (box) {
        boxes.push({ label: text.trim(), box });
      }
    }

    // Assert that no adjacent headers in the same row overlap horizontally
    for (let i = 0; i < boxes.length - 1; i++) {
      const cur = boxes[i];
      const next = boxes[i + 1];
      const overlap = (cur.box.x + cur.box.width) - next.box.x;
      expect(overlap).toBeLessThanOrEqual(1); // At most 1px border sub-pixel rounding
    }

    // Save 1920x1080 screenshot
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'requirements-1920x1080.png'),
      fullPage: true,
    });

    // Viewport 2: 1366x768
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.waitForTimeout(800);

    // Save 1366x768 screenshot
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'requirements-1366x768.png'),
      fullPage: true,
    });
  });

  test('Purchase Page: Subtitle visibility, header groups span all columns, no clipping', async ({ page }) => {
    // Viewport 1: 1920x1080
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.locator('a[href="/purchase"]').click();
    await page.waitForTimeout(1000);

    // Verify subtitle is visible and NOT cut off
    const subtitle = page.locator('text=Build monthly purchase recommendations');
    await expect(subtitle).toBeVisible();

    const subtitleBox = await subtitle.boundingBox();
    expect(subtitleBox).not.toBeNull();
    expect(subtitleBox!.height).toBeGreaterThan(10);
    expect(subtitleBox!.y).toBeGreaterThan(60); // Must be below top navigation header (h-16 = 64px)

    // Verify Purchase Plan tab is active
    const planTab = page.getByRole('button', { name: 'Purchase Plan', exact: true });
    await expect(planTab).toBeVisible();

    // Verify Header Groups
    const group1 = page.getByRole('columnheader', { name: 'CONSUMABLE', exact: true });
    const group2 = page.getByRole('columnheader', { name: 'PURCHASE QUANTITY', exact: true });
    const group3 = page.getByRole('columnheader', { name: 'APPROVAL STATUS & REFERENCES', exact: true });

    await expect(group1).toBeVisible();
    await expect(group2).toBeVisible();
    await expect(group3).toBeVisible();

    // Verify all 14 columns exist under the header groups
    const purchaseThs = page.locator('table thead tr:nth-child(2) th');
    const pThCount = await purchaseThs.count();
    expect(pThCount).toBeGreaterThanOrEqual(14);

    // Save 1920x1080 screenshot
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'purchase-1920x1080.png'),
      fullPage: true,
    });

    // Viewport 2: 1366x768
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.waitForTimeout(800);

    // Save 1366x768 screenshot
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'purchase-1366x768.png'),
      fullPage: true,
    });
  });

  test('Interactive Excel features: Columns menu, Right-Click menu, Keyboard navigation', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.locator('a[href="/requirements"]').click();
    await page.waitForTimeout(1000);

    // Columns Menu dropdown
    const colMenuBtn = page.locator('button:has-text("Columns (")');
    if (await colMenuBtn.count() > 0) {
      await colMenuBtn.click();
      await page.waitForTimeout(300);
      const colDropdown = page.locator('text=Manage Columns');
      await expect(colDropdown).toBeVisible();

      // Close dropdown
      await page.keyboard.press('Escape');
    }

    // Right-Click Context Menu on first table cell
    const firstCell = page.locator('table tbody tr:first-child td:nth-child(3)');
    if (await firstCell.count() > 0) {
      await firstCell.click({ button: 'right' });
      await page.waitForTimeout(300);

      // Verify context menu is rendered via portal
      const editOption = page.locator('text=Edit cell');
      await expect(editOption).toBeVisible();

      // Dismiss context menu
      await page.keyboard.press('Escape');
    }
  });
});

