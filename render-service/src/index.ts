import express, { Request, Response, NextFunction } from "express";
import { createLogger, format, transports } from "winston";
import { renderSlide, RenderRequest, RenderResult, setBrowserPool, getBrowserPool, AVAILABLE_FONTS } from "./renderer.js";
import { BrowserPool } from "./browser-pool.js";
import { z } from "zod";
import fs from "fs";

const PORT = process.env.PORT || 3001;
const LOG_LEVEL = process.env.LOG_LEVEL || "info";
const POOL_SIZE = parseInt(process.env.POOL_SIZE || "3", 10);
const MAX_CONCURRENCY = parseInt(process.env.MAX_CONCURRENCY || "3", 10);

// Render limits to prevent DoS
const MAX_DURATION = parseInt(process.env.MAX_DURATION || "300", 10); // 5 minutes
const MAX_FPS = parseInt(process.env.MAX_FPS || "60", 10);
const MAX_WIDTH = parseInt(process.env.MAX_WIDTH || "3840", 10); // 4K
const MAX_HEIGHT = parseInt(process.env.MAX_HEIGHT || "2160", 10); // 4K
const MAX_FRAMES = parseInt(process.env.MAX_FRAMES || "18000", 10); // 5min @ 60fps

// Logger setup
const logger = createLogger({
  level: LOG_LEVEL,
  format: format.combine(
    format.timestamp(),
    format.errors({ stack: true }),
    format.json()
  ),
  transports: [new transports.Console()],
});

// Browser pool (initialized at startup)
let browserPool: BrowserPool;

// Express app
const app = express();
app.use(express.json({ limit: "50mb" }));

// SECURITY: Strict validation patterns
const SAFE_ID_REGEX = /^[a-zA-Z0-9_-]+$/; // Only alphanumeric, underscore, dash
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
const RGB_COLOR_REGEX = /^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*(0|1|0?\.\d+))?\s*\)$/;

// Safe color validator (hex or rgb/rgba only)
const safeColorSchema = z.string().refine(
  (val) => HEX_COLOR_REGEX.test(val) || RGB_COLOR_REGEX.test(val),
  { message: "Color must be hex (#RGB, #RRGGBB, #RRGGBBAA) or rgb()/rgba()" }
);

// Safe ID validator (alphanumeric only, prevents HTML/CSS injection)
const safeIdSchema = z.string().min(1).max(100).regex(SAFE_ID_REGEX, {
  message: "ID must contain only alphanumeric characters, underscore, or dash"
});

// Font family whitelist validator
const fontFamilySchema = z.enum(AVAILABLE_FONTS as unknown as [string, ...string[]]).optional();

// Text style schema with strict validation
// Note: fontSize/minFontSize accept floats because Python sends 32.0 not 32
const TextStyleSchema = z.object({
  fontFamily: fontFamilySchema,
  fontSize: z.number().positive().max(500).optional(),
  fontWeight: z.enum(["normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"]).optional(),
  fontStyle: z.enum(["normal", "italic"]).optional(),
  color: safeColorSchema.optional(),
  align: z.enum(["left", "center", "right", "justify"]).optional(),
  verticalAlign: z.enum(["top", "middle", "bottom"]).optional(),
  lineHeight: z.number().positive().max(10).optional(),
}).strict().optional();

// Text content schema
const TextContentSchema = z.object({
  baseContent: z.string().max(10000),
  translations: z.record(z.string(), z.string().max(10000)).optional(),
  isTranslatable: z.boolean().optional(),
  style: TextStyleSchema,
  overflow: z.enum(["shrinkFont", "expandHeight", "clip"]).optional(),
  minFontSize: z.number().positive().max(500).optional(),
}).strict().optional();

// Plate content schema
const PlateContentSchema = z.object({
  backgroundColor: safeColorSchema,
  backgroundOpacity: z.number().min(0).max(1).optional(),
  borderRadius: z.number().int().min(0).max(1000).optional(),
  border: z.object({
    color: safeColorSchema,
    width: z.number().int().min(0).max(100),
  }).strict().optional(),
  padding: z.object({
    top: z.number().int().min(0).max(1000),
    right: z.number().int().min(0).max(1000),
    bottom: z.number().int().min(0).max(1000),
    left: z.number().int().min(0).max(1000),
  }).strict().optional(),
}).strict().optional();

// Image content schema
const ImageContentSchema = z.object({
  assetId: safeIdSchema,
  assetUrl: z.string().min(1).max(2000),
  fit: z.enum(["contain", "cover", "fill"]).optional(),
}).strict().optional();

// Animation trigger schema
const AnimationTriggerSchema = z.object({
  type: z.enum(["time", "start", "end", "marker", "word"]),
  seconds: z.number().min(0).optional(),
  offsetSeconds: z.number().optional(),
  markerId: safeIdSchema.optional(),
  charStart: z.number().int().min(0).optional(),
  charEnd: z.number().int().min(0).optional(),
  wordText: z.string().max(1000).optional(),
}).strict();

// Animation config schema
const AnimationConfigSchema = z.object({
  type: z.enum(["none", "fadeIn", "fadeOut", "slideLeft", "slideRight", "slideUp", "slideDown"]),
  duration: z.number().min(0).max(60),
  delay: z.number().min(0).max(300).optional(),
  easing: z.enum(["linear", "easeIn", "easeOut", "easeInOut"]).optional(),
  trigger: AnimationTriggerSchema,
}).strict();

// Layer animation schema
const LayerAnimationSchema = z.object({
  entrance: AnimationConfigSchema.optional(),
  exit: AnimationConfigSchema.optional(),
}).strict().optional();

// Position and size schemas
const LayerPositionSchema = z.object({
  x: z.number().min(-10000).max(10000),
  y: z.number().min(-10000).max(10000),
}).strict();

const LayerSizeSchema = z.object({
  width: z.number().positive().max(10000),
  height: z.number().positive().max(10000),
}).strict();

// SECURITY: Strict layer schema - validates all fields that could be injected into HTML/CSS
const SlideLayerSchema = z.object({
  id: safeIdSchema,
  type: z.enum(["text", "image", "plate"]),
  name: z.string().max(200),
  position: LayerPositionSchema,
  size: LayerSizeSchema,
  rotation: z.number().min(-360).max(360).optional(),
  opacity: z.number().min(0).max(1).optional(),
  visible: z.boolean().optional(),
  locked: z.boolean().optional(),
  zIndex: z.number().int().min(-1000).max(1000),
  groupId: safeIdSchema.optional(),
  text: TextContentSchema,
  plate: PlateContentSchema,
  image: ImageContentSchema,
  animation: LayerAnimationSchema,
}).strict();

// Request validation schema with upper bounds
const RenderRequestSchema = z.object({
  slideId: z.string().uuid(),
  // Can be HTTP/HTTPS URL or absolute filesystem path (preferred in Docker)
  // NOTE: file: URLs are rejected by renderer for security
  slideImageUrl: z.string().min(1).max(2000),
  layers: z.array(SlideLayerSchema).max(100), // Limit layer count
  duration: z.number().positive().max(MAX_DURATION),
  width: z.number().int().positive().max(MAX_WIDTH).default(1920),
  height: z.number().int().positive().max(MAX_HEIGHT).default(1080),
  fps: z.number().int().positive().max(MAX_FPS).default(30),
  format: z.enum(["webm", "mp4"]).default("webm"),
  renderKey: z.string().max(200).optional(),
  lang: z.string().max(10).optional(),
}).refine(
  // Prevent excessive frame count (DoS protection)
  (data) => Math.ceil(data.duration * data.fps) <= MAX_FRAMES,
  { message: `Total frame count exceeds maximum (${MAX_FRAMES}). Reduce duration or fps.` }
);

// Preview request schema (simpler - just one frame, no animation)
const PreviewRequestSchema = z.object({
  slideId: z.string().uuid(),
  slideImageUrl: z.string().min(1).max(2000),
  layers: z.array(SlideLayerSchema).max(100),
  width: z.number().int().positive().max(MAX_WIDTH).default(1920),
  height: z.number().int().positive().max(MAX_HEIGHT).default(1080),
  lang: z.string().max(10).optional(),
});

// Health check with pool stats
app.get("/health", (_req: Request, res: Response) => {
  const pool = getBrowserPool();
  const poolStats = pool ? pool.getStats() : null;
  
  res.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    pool: poolStats,
    config: {
      poolSize: POOL_SIZE,
      maxConcurrency: MAX_CONCURRENCY,
    },
  });
});

// Render endpoint
app.post("/render", async (req: Request, res: Response, next: NextFunction) => {
  const startTime = Date.now();
  
  try {
    // Validate request
    const parsed = RenderRequestSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({
        error: "Invalid request",
        details: parsed.error.issues,
      });
      return;
    }

    const request: RenderRequest = parsed.data;
    
    logger.info("Starting render", {
      slideId: request.slideId,
      duration: request.duration,
      layers: request.layers.length,
      renderKey: request.renderKey,
    });

    // Perform render
    const result: RenderResult = await renderSlide(request, logger);

    const elapsed = Date.now() - startTime;
    logger.info("Render complete", {
      slideId: request.slideId,
      elapsed: `${elapsed}ms`,
      outputPath: result.outputPath,
    });

    res.json({
      success: true,
      slideId: result.slideId,
      outputPath: result.outputPath,
      duration: result.duration,
      frames: result.frames,
      elapsed,
    });
  } catch (error) {
    next(error);
  }
});

// Preview endpoint - generates a single PNG frame with layers overlay
app.post("/render-preview", async (req: Request, res: Response, next: NextFunction) => {
  const startTime = Date.now();
  
  try {
    // Validate request
    const parsed = PreviewRequestSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({
        error: "Invalid request",
        details: parsed.error.issues,
      });
      return;
    }

    const { slideId, slideImageUrl, layers, width, height, lang } = parsed.data;
    
    logger.info("Starting preview render", {
      slideId,
      layers: layers.length,
      width,
      height,
    });

    // Import renderPreview from renderer
    const { renderPreview } = await import("./renderer.js");
    
    const result = await renderPreview({
      slideId,
      slideImageUrl,
      layers,
      width,
      height,
      lang,
    }, logger);

    const elapsed = Date.now() - startTime;
    logger.info("Preview render complete", {
      slideId,
      elapsed: `${elapsed}ms`,
      outputPath: result.outputPath,
    });

    res.json({
      success: true,
      slideId: result.slideId,
      outputPath: result.outputPath,
      elapsed,
    });
  } catch (error) {
    next(error);
  }
});

// Render batch endpoint (multiple slides) with PARALLEL processing
app.post("/render-batch", async (req: Request, res: Response, next: NextFunction) => {
  const startTime = Date.now();
  
  try {
    const { slides, concurrency: reqConcurrency } = req.body;
    
    if (!Array.isArray(slides) || slides.length === 0) {
      res.status(400).json({ error: "slides array is required" });
      return;
    }

    // SECURITY: Validate concurrency is a positive integer to prevent NaN
    const parsedConcurrency = typeof reqConcurrency === "number" && 
                              Number.isFinite(reqConcurrency) && 
                              reqConcurrency > 0 
                              ? Math.floor(reqConcurrency) 
                              : MAX_CONCURRENCY;
    
    // Use requested concurrency capped by MAX_CONCURRENCY and POOL_SIZE
    const concurrency = Math.min(
      parsedConcurrency,
      MAX_CONCURRENCY,
      slides.length,
      POOL_SIZE
    );

    logger.info("Starting batch render", { 
      count: slides.length, 
      concurrency,
      poolStats: getBrowserPool()?.getStats(),
    });

    // Validate all slides first
    const validSlides: RenderRequest[] = [];
    for (const slideData of slides) {
      const parsed = RenderRequestSchema.safeParse(slideData);
      if (!parsed.success) {
        logger.warn("Skipping invalid slide", { errors: parsed.error.issues });
        continue;
      }
      validSlides.push(parsed.data);
    }

    if (validSlides.length === 0) {
      res.json({
        success: true,
        results: [],
        stats: {
          total: slides.length,
          success: 0,
          failed: 0,
          elapsed: Date.now() - startTime,
          avgPerSlide: 0,
          concurrency,
        },
      });
      return;
    }

    // Parallel render with concurrency limit
    const results: (RenderResult | { error: string; slideId: string })[] = [];
    const queue = [...validSlides];
    const inFlight: Promise<void>[] = [];

    const processNext = async (): Promise<void> => {
      if (queue.length === 0) return;
      
      const slide = queue.shift()!;
      try {
        const result = await renderSlide(slide, logger);
        results.push(result);
      } catch (error) {
        logger.error("Slide render failed", { slideId: slide.slideId, error });
        results.push({ 
          error: error instanceof Error ? error.message : "Unknown error",
          slideId: slide.slideId,
        });
      }
      
      // Process next if queue not empty
      if (queue.length > 0) {
        await processNext();
      }
    };

    // Start initial batch of concurrent renders
    for (let i = 0; i < concurrency && i < validSlides.length; i++) {
      inFlight.push(processNext());
    }

    // Wait for all to complete
    await Promise.all(inFlight);

    const elapsed = Date.now() - startTime;
    const successCount = results.filter((r) => "outputPath" in r).length;
    const avgPerSlide = results.length > 0 ? Math.round(elapsed / results.length) : 0;
    
    logger.info("Batch render complete", {
      total: slides.length,
      success: successCount,
      failed: results.length - successCount,
      elapsed: `${elapsed}ms`,
      avgPerSlide: `${avgPerSlide}ms`,
    });

    res.json({
      success: true,
      results,
      stats: {
        total: slides.length,
        success: successCount,
        failed: results.length - successCount,
        elapsed,
        avgPerSlide,
        concurrency,
      },
    });
  } catch (error) {
    next(error);
  }
});

// Error handler
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  logger.error("Request error", { error: err.message, stack: err.stack });
  res.status(500).json({
    error: "Internal server error",
    message: err.message,
  });
});

// Initialize browser pool and start server
async function startServer(): Promise<void> {
  // SECURITY: Verify Puppeteer executable exists
  const puppeteerPath = process.env.PUPPETEER_EXECUTABLE_PATH;
  if (puppeteerPath) {
    if (!fs.existsSync(puppeteerPath)) {
      logger.error("PUPPETEER_EXECUTABLE_PATH does not exist", { path: puppeteerPath });
      throw new Error(`Chromium binary not found at: ${puppeteerPath}`);
    }
    logger.info("Using Chromium binary", { path: puppeteerPath });
  }
  
  logger.info("Initializing browser pool...", { poolSize: POOL_SIZE });
  
  browserPool = new BrowserPool({
    poolSize: POOL_SIZE,
    viewport: { width: 1920, height: 1080 },
    logger,
  });
  
  await browserPool.initialize();
  setBrowserPool(browserPool);
  
  logger.info("Browser pool ready", browserPool.getStats());
  
  const server = app.listen(PORT, () => {
    logger.info(`Render service started on port ${PORT}`, {
      poolSize: POOL_SIZE,
      maxConcurrency: MAX_CONCURRENCY,
    });
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    logger.info(`Received ${signal}, shutting down gracefully...`);
    
    server.close(async () => {
      logger.info("HTTP server closed");
      
      if (browserPool) {
        await browserPool.shutdown();
        logger.info("Browser pool closed");
      }
      
      process.exit(0);
    });

    // Force exit after 30 seconds
    setTimeout(() => {
      logger.error("Forced shutdown after timeout");
      process.exit(1);
    }, 30000);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

// Start the server
startServer().catch((error) => {
  logger.error("Failed to start server", { error: error.message, stack: error.stack });
  process.exit(1);
});

export { app };

