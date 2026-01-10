/**
 * Browser Pool - Manages a pool of Puppeteer pages for parallel rendering
 * 
 * Benefits:
 * - Single browser instance (saves ~1.5s per render)
 * - Pre-warmed pages ready to use
 * - Parallel rendering support
 * - Automatic crash recovery
 */
import puppeteer, { Browser, Page } from "puppeteer";
import { EventEmitter } from "events";
import { Logger } from "winston";

export interface BrowserPoolConfig {
  poolSize: number;
  viewport: { width: number; height: number };
  logger: Logger;
}

export class BrowserPool extends EventEmitter {
  private browser: Browser | null = null;
  private availablePages: Page[] = [];
  private busyPages: Set<Page> = new Set();
  private waitingQueue: Array<{ resolve: (page: Page) => void; reject: (err: Error) => void }> = [];
  private config: BrowserPoolConfig;
  private initialized = false;
  private initializing = false;
  private restarting = false; // Mutex flag to prevent concurrent restarts
  private healthCheckInterval: NodeJS.Timeout | null = null;

  constructor(config: BrowserPoolConfig) {
    super();
    this.config = config;
  }

  /**
   * Initialize the browser pool
   */
  async initialize(): Promise<void> {
    if (this.initialized || this.initializing) return;
    this.initializing = true;

    const { logger, poolSize, viewport } = this.config;
    logger.info("Initializing browser pool", { poolSize });

    try {
      const protocolTimeoutMs = parseInt(process.env.PUPPETEER_PROTOCOL_TIMEOUT_MS || "600000", 10);

      this.browser = await puppeteer.launch({
        headless: true,
        protocolTimeout: protocolTimeoutMs,
        args: [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
          "--disable-gpu",
          "--disable-software-rasterizer",
          // SECURITY NOTE: --disable-web-security and --allow-file-access-from-files
          // are required for loading local slide images and assets via file:// URLs.
          //
          // MITIGATION: Access is restricted via path whitelist in renderer.ts:
          // 1. normalizeSrc() validates all file paths against ALLOWED_BASE_PATHS
          // 2. Only paths under /data/projects (or configured bases) are allowed
          // 3. file: URLs passed directly are rejected
          // 4. Path normalization prevents ../ directory traversal attacks
          //
          // The render-service runs in an isolated Docker container with no network
          // egress, limiting the blast radius of any potential path bypass.
          "--allow-file-access-from-files",
          "--disable-web-security",
          // Performance optimizations
          "--disable-extensions",
          "--disable-background-networking",
          "--disable-background-timer-throttling",
          "--disable-backgrounding-occluded-windows",
          "--disable-breakpad",
          "--disable-component-update",
          "--disable-default-apps",
          "--disable-hang-monitor",
          "--disable-ipc-flooding-protection",
          "--disable-popup-blocking",
          "--disable-prompt-on-repost",
          "--disable-renderer-backgrounding",
          "--disable-sync",
          "--disable-translate",
          "--metrics-recording-only",
          "--no-first-run",
          "--safebrowsing-disable-auto-update",
        ],
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
      });

      // Create page pool
      for (let i = 0; i < poolSize; i++) {
        const page = await this.createPage(viewport);
        this.availablePages.push(page);
      }

      this.initialized = true;
      this.initializing = false;

      // Start health check
      this.startHealthCheck();

      logger.info("Browser pool initialized", {
        poolSize,
        availablePages: this.availablePages.length,
      });
    } catch (error) {
      this.initializing = false;
      throw error;
    }
  }

  /**
   * Create a new page with viewport settings
   */
  private async createPage(viewport: { width: number; height: number }): Promise<Page> {
    if (!this.browser) throw new Error("Browser not initialized");

    const page = await this.browser.newPage();
    await page.setViewport({ ...viewport, deviceScaleFactor: 1 });

    // Set a reasonable default navigation timeout
    page.setDefaultNavigationTimeout(60000);
    page.setDefaultTimeout(60000);

    return page;
  }

  /**
   * Acquire a page from the pool (waits if none available)
   */
  async acquire(): Promise<Page> {
    if (!this.initialized) {
      await this.initialize();
    }

    // If page available, return immediately
    if (this.availablePages.length > 0) {
      const page = this.availablePages.pop()!;
      this.busyPages.add(page);
      return page;
    }

    // Wait for a page to become available (with reject capability for error handling)
    return new Promise((resolve, reject) => {
      this.waitingQueue.push({ resolve, reject });
    });
  }

  /**
   * Release a page back to the pool
   */
  async release(page: Page): Promise<void> {
    this.busyPages.delete(page);

    let pageToReturn: Page | null = page;
    
    // Reset page state for reuse
    try {
      // Navigate to blank page to reset state
      await page.goto("about:blank", { waitUntil: "domcontentloaded", timeout: 5000 });
    } catch {
      // Page might be closed/crashed, create a new one
      this.config.logger.warn("Page reset failed, creating new page");
      try {
        await page.close();
      } catch {
        // ignore
      }
      try {
        pageToReturn = await this.createPage(this.config.viewport);
      } catch (error) {
        this.config.logger.error("Failed to create replacement page", { error });
        pageToReturn = null;
        
        // SECURITY FIX: If we can't create a replacement page, we need to:
        // 1. Try to restart the pool to recover
        // 2. Or reject waiting requests so they don't hang forever
        if (this.waitingQueue.length > 0) {
          this.config.logger.warn("Rejecting waiting request due to page creation failure");
          const waiter = this.waitingQueue.shift()!;
          waiter.reject(new Error("Browser pool unhealthy: failed to create page"));
        }
        
        // Trigger async restart to try to recover
        this.restart().catch((restartErr) => {
          this.config.logger.error("Failed to restart pool after page creation failure", { error: restartErr });
        });
        return;
      }
    }

    // If someone is waiting, give them the page
    if (pageToReturn && this.waitingQueue.length > 0) {
      const waiter = this.waitingQueue.shift()!;
      this.busyPages.add(pageToReturn);
      waiter.resolve(pageToReturn);
    } else if (pageToReturn) {
      this.availablePages.push(pageToReturn);
    }
  }

  /**
   * Get pool statistics
   */
  getStats(): { available: number; busy: number; waiting: number } {
    return {
      available: this.availablePages.length,
      busy: this.busyPages.size,
      waiting: this.waitingQueue.length,
    };
  }

  /**
   * Start periodic health check
   */
  private startHealthCheck(): void {
    this.healthCheckInterval = setInterval(() => {
      // SECURITY FIX: Wrap async restart in try/catch to prevent UnhandledPromiseRejection
      if (!this.browser || !this.browser.isConnected()) {
        this.config.logger.warn("Browser disconnected, restarting...");
        this.restart().catch((error) => {
          this.config.logger.error("Health check restart failed", { 
            error: error instanceof Error ? error.message : String(error) 
          });
        });
      }
    }, 10000); // Check every 10 seconds
  }

  /**
   * Restart the browser pool (for crash recovery)
   */
  async restart(): Promise<void> {
    // SECURITY FIX: Mutex to prevent concurrent restarts
    if (this.restarting) {
      this.config.logger.warn("Restart already in progress, skipping");
      return;
    }
    
    this.restarting = true;
    this.config.logger.info("Restarting browser pool...");

    // Preserve waiting requests so we can fulfill (or fail) them after restart
    const waiting = [...this.waitingQueue];
    this.waitingQueue = [];

    try {

      // Close existing browser
      if (this.browser) {
        try {
          await this.browser.close();
        } catch {
          // ignore
        }
      }

      // Reset state
      this.browser = null;
      this.availablePages = [];
      this.busyPages.clear();
      this.initialized = false;
      this.initializing = false;

      // Re-initialize
      await this.initialize();

      // Fulfill any requests that were waiting
      // (if pool is smaller than waiting count, the rest will continue waiting)
      for (const waiter of waiting) {
        if (this.availablePages.length > 0) {
          const page = this.availablePages.pop()!;
          this.busyPages.add(page);
          waiter.resolve(page);
        } else {
          this.waitingQueue.push(waiter);
        }
      }
    } catch (error) {
      // IMPORTANT: If restart fails, reject preserved waiters so acquire() doesn't hang forever.
      const err = error instanceof Error ? error : new Error(String(error));
      for (const waiter of waiting) {
        try {
          waiter.reject(err);
        } catch {
          // ignore
        }
      }
      throw err;
    } finally {
      this.restarting = false;
    }
  }

  /**
   * Shutdown the pool gracefully
   */
  async shutdown(): Promise<void> {
    this.config.logger.info("Shutting down browser pool...");

    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
    }

    // Reject any waiting acquire() callers so they don't hang during shutdown
    if (this.waitingQueue.length > 0) {
      const err = new Error("Browser pool is shutting down");
      for (const waiter of this.waitingQueue) {
        try {
          waiter.reject(err);
        } catch {
          // ignore
        }
      }
      this.waitingQueue = [];
    }

    // Close all pages
    for (const page of this.availablePages) {
      try {
        await page.close();
      } catch {
        // ignore
      }
    }
    for (const page of this.busyPages) {
      try {
        await page.close();
      } catch {
        // ignore
      }
    }

    // Close browser
    if (this.browser) {
      try {
        await this.browser.close();
      } catch {
        // ignore
      }
    }

    this.initialized = false;
  }
}

