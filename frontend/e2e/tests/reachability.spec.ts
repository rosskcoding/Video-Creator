/**
 * Reachability Audit Tests (R-01 to R-02)
 * 
 * Цель: каждая заявленная фича имеет видимый вход из UI.
 * 
 * Test Matrix:
 * - R-01: Карта входов (каждая фича имеет кнопку/меню/ссылку)
 * - R-02: Нет "мертвых" страниц (все страницы достижимы ≤ 3 клика)
 */
import { test, expect } from '@playwright/test';

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
  
  // Wait for redirect - either to home or projects page
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('h1:has-text("Projects")', { timeout: 10000 });
}

test.describe('R-01: Feature Entry Points', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('R-01.1: Home page has create project button', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Should have visible "New Project" button
    const createButton = page.locator('button:has-text("New Project")');
    await expect(createButton).toBeVisible();
  });

  test('R-01.2: Project list accessible from home', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Projects heading should be visible
    const projectsHeading = page.locator('h1:has-text("Projects")');
    await expect(projectsHeading).toBeVisible();
  });

  test('R-01.3: Workspace accessible from navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Should have workspace link in navigation
    const workspaceLink = page.locator('a[href="/workspace"]');
    await expect(workspaceLink).toBeVisible();
  });

  test('R-01.4: Admin/Jobs accessible from navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Should have jobs link in navigation
    const jobsLink = page.locator('a[href="/admin/jobs"]');
    await expect(jobsLink).toBeVisible();
  });

  test('R-01.5: Help page accessible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Should have help link
    const helpLink = page.locator('a[href="/help"]');
    await expect(helpLink).toBeVisible();
  });
  
  test('R-01.6: Admin link accessible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Should have admin link
    const adminLink = page.locator('a[href="/admin"]');
    await expect(adminLink).toBeVisible();
  });
});

test.describe('R-02: Page Reachability', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('R-02.1: Home is accessible directly', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    await expect(page).toHaveURL('/');
    // Page loads without error
    await expect(page.locator('body')).toBeVisible();
  });

  test('R-02.2: Workspace reachable in ≤2 clicks from home', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Click workspace link
    await page.click('a[href="/workspace"]');
    await page.waitForURL('/workspace');
    
    await expect(page).toHaveURL('/workspace');
  });

  test('R-02.3: Admin Jobs reachable in ≤2 clicks', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Navigate to jobs
    await page.click('a[href="/admin/jobs"]');
    await page.waitForURL('/admin/jobs');
    
    await expect(page).toHaveURL('/admin/jobs');
  });

  test('R-02.4: Project editor reachable in ≤2 clicks', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Click on first project card link
    const projectCard = page.locator('main a[href^="/projects/"]').first();
    
    if (await projectCard.isVisible()) {
      await projectCard.click();
      await page.waitForURL(/\/projects\//);
      await expect(page).toHaveURL(/\/projects\/.+/);
    }
  });

  test('R-02.5: Project settings reachable from project page', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const projectCard = page.locator('main a[href^="/projects/"]').first();
    
    if (await projectCard.isVisible()) {
      await projectCard.click();
      await page.waitForURL(/\/projects\//);
      await page.waitForLoadState('networkidle');
      
      // Settings tab or link should be accessible
      const settingsLink = page.locator('a[href*="settings"]');
      await expect(settingsLink.first()).toBeVisible({ timeout: 10000 });
    }
  });

  test('R-02.6: Login page accessible when logged out', async ({ page, context }) => {
    // Clear cookies to log out
    await context.clearCookies();
    
    await page.goto('/login');
    await expect(page).toHaveURL('/login');
    
    // Login form should be visible
    await expect(page.locator('input[placeholder="Enter username"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Enter password"]')).toBeVisible();
  });
  
  test('R-02.7: Help page loads correctly', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    await page.click('a[href="/help"]');
    await page.waitForURL('/help');
    
    await expect(page).toHaveURL('/help');
  });
});

test.describe('R-03: Navigation Consistency', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('R-03.1: Sidebar/Navigation visible on all main pages', async ({ page }) => {
    const pages = ['/', '/workspace', '/admin/jobs'];
    
    for (const path of pages) {
      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);
      
      // Navigation should be visible
      const nav = page.locator('nav');
      await expect(nav.first()).toBeVisible({ timeout: 10000 });
    }
  });

  test('R-03.2: Can navigate back to home from any page', async ({ page }) => {
    const pages = ['/workspace', '/admin/jobs', '/help'];
    
    for (const path of pages) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      
      // Projects link should navigate to home
      const homeLink = page.locator('a[href="/"]').first();
      
      if (await homeLink.isVisible()) {
        await homeLink.click();
        await page.waitForURL('/');
        await expect(page).toHaveURL('/');
      }
    }
  });
});
