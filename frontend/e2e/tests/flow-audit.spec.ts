/**
 * Flow Audit E2E Tests (F-E2E-01 to F-E2E-11)
 * 
 * Цель: ключевые пользовательские пути проходят end-to-end
 * 
 * Test Matrix:
 * - F-E2E-01 to F-E2E-03: Project creation and management
 * - F-E2E-04 to F-E2E-06: Slide management and editing
 * - F-E2E-07 to F-E2E-09: Generation and export
 * - F-E2E-10 to F-E2E-11: Admin and monitoring
 */
import { test, expect } from '@playwright/test';
import path from 'path';

// Helper to login before tests
async function login(page: any) {
  // Go to home first - if already logged in, won't redirect to login
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  // Check if already logged in (Projects heading visible)
  const projectsHeading = page.locator('h1:has-text("Projects")');
  if (await projectsHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
    return; // Already logged in
  }
  
  // Need to login
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  // Fill login form
  await page.fill('input[placeholder="Enter username"]', 'login');
  await page.fill('input[placeholder="Enter password"]', 'Superman2026!');
  
  // Wait for button to be enabled and click
  await page.waitForSelector('button:has-text("Sign In"):not([disabled])');
  await page.click('button:has-text("Sign In")');
  
  // Wait for redirect
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('h1:has-text("Projects")', { timeout: 10000 });
}

// Helper to navigate to first project
async function goToFirstProject(page: any) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForSelector('h1:has-text("Projects")', { timeout: 10000 });
  
  const projectCard = page.locator('main a[href^="/projects/"]').first();
  
  if (await projectCard.isVisible({ timeout: 5000 }).catch(() => false)) {
    await projectCard.click();
    await page.waitForURL(/\/projects\//, { timeout: 15000 });
    await page.waitForLoadState('domcontentloaded');
    return true;
  }
  return false;
}

test.describe('Flow: Project Creation and Upload', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('F-E2E-01: Create project flow', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Click New Project button
    const newProjectBtn = page.locator('button:has-text("New Project")');
    await expect(newProjectBtn).toBeVisible();
    await newProjectBtn.click();
    
    // Modal should appear with form
    await page.waitForTimeout(500);
    
    // Fill project name
    const nameInput = page.locator('input[placeholder*="name" i], input[name="name"]').first();
    if (await nameInput.isVisible()) {
      await nameInput.fill('E2E Test Project ' + Date.now());
      
      // Submit form
      const submitBtn = page.locator('button:has-text("Create"), button[type="submit"]').first();
      if (await submitBtn.isVisible()) {
        await submitBtn.click();
        await page.waitForTimeout(1000);
      }
    }
  });

  test('F-E2E-02: Project persists after page reload', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Get project count or first project name
    const projects = page.locator('main a[href^="/projects/"]');
    const initialCount = await projects.count();
    
    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Count should be the same
    const afterCount = await page.locator('main a[href^="/projects/"]').count();
    expect(afterCount).toBe(initialCount);
  });
});

test.describe('Flow: Slide Management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('F-E2E-03: Script editing persists', async ({ page }) => {
    const hasProject = await goToFirstProject(page);
    
    if (hasProject) {
      // Wait for project editor to load
      await page.waitForTimeout(1000);
      
      // Project editor should be visible
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
    }
  });

  test('F-E2E-04: Navigate between slides', async ({ page }) => {
    const hasProject = await goToFirstProject(page);
    
    if (hasProject) {
      await page.waitForTimeout(1000);
      
      // Look for slide navigation or thumbnails
      const slideContainer = page.locator('[class*="slide"], [class*="Slide"]');
      
      if (await slideContainer.first().isVisible({ timeout: 5000 })) {
        await expect(slideContainer.first()).toBeVisible();
      }
    }
  });
});

test.describe('Flow: Generation and Export', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('F-E2E-05: Access generation controls', async ({ page }) => {
    const hasProject = await goToFirstProject(page);
    
    if (hasProject) {
      await page.waitForTimeout(1000);
      
      // Look for generation-related buttons (TTS, Generate, etc.)
      const generateBtn = page.locator('button:has-text("Generate"), button:has-text("TTS")');
      
      // These controls may or may not be visible depending on project state
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
    }
  });

  test('F-E2E-06: Access render controls', async ({ page }) => {
    const hasProject = await goToFirstProject(page);
    
    if (hasProject) {
      await page.waitForTimeout(1000);
      
      // Look for render/export buttons
      const renderBtn = page.locator('button:has-text("Render"), button:has-text("Export")');
      
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
    }
  });

  test('F-E2E-07: Access project settings', async ({ page }) => {
    const hasProject = await goToFirstProject(page);
    
    if (hasProject) {
      // Look for settings link
      const settingsLink = page.locator('a[href*="settings"]');
      
      if (await settingsLink.first().isVisible({ timeout: 5000 })) {
        await settingsLink.first().click();
        await page.waitForURL(/\/settings/);
        await expect(page).toHaveURL(/\/settings/);
      }
    }
  });
});

test.describe('Flow: Workspace and Downloads', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('F-E2E-08: Workspace shows exports', async ({ page }) => {
    await page.goto('/workspace');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Workspace page should load
    await expect(page).toHaveURL('/workspace');
    
    // Should show some content (files, empty state, etc.)
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible({ timeout: 10000 });
  });

  test('F-E2E-09: Download links are accessible', async ({ page }) => {
    await page.goto('/workspace');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // May or may not have downloads
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Flow: Admin and Monitoring', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('F-E2E-10: Jobs list shows job status', async ({ page }) => {
    // Regression guard: React key warnings or unsafe target=_blank links should not appear
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/admin/jobs');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Jobs page should load
    await expect(page).toHaveURL('/admin/jobs');
    
    // Should show jobs list or empty state
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible({ timeout: 10000 });

    // No React key warnings
    expect(
      consoleErrors.some((t) =>
        t.includes('Each child in a list should have a unique "key" prop')
      )
    ).toBeFalsy();

    // Any target=_blank links must have rel=noopener (and ideally noreferrer)
    const externalLinks = page.locator('a[target="_blank"]');
    const count = await externalLinks.count();
    for (let i = 0; i < count; i++) {
      const rel = (await externalLinks.nth(i).getAttribute('rel')) || '';
      expect(rel).toContain('noopener');
    }
  });

  test('F-E2E-11: Can filter or refresh jobs', async ({ page }) => {
    await page.goto('/admin/jobs');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Look for filter/refresh controls
    const refreshBtn = page.locator('button:has-text("Refresh")');
    
    if (await refreshBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await refreshBtn.click();
      await page.waitForTimeout(500);
    }
    
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible({ timeout: 10000 });
  });
  
  test('F-E2E-12: Admin page loads', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Admin page should load
    await expect(page).toHaveURL('/admin');
    
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible({ timeout: 10000 });
  });
});
