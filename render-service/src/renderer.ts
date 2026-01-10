/**
 * EPIC B: Optimized Render Service
 * 
 * Key improvements:
 * 1. In-memory screenshot capture (no PNG files on disk)
 * 2. Direct pipe to ffmpeg via stdin (image2pipe)
 * 3. Deterministic timeline control via __setTimelineTime
 * 4. Segment caching support
 */
import { Page } from "puppeteer";
import { v4 as uuidv4 } from "uuid";
import path from "path";
import fs from "fs/promises";
import { existsSync } from "fs";
import { spawn, ChildProcess } from "child_process";
import { Logger } from "winston";
import { pathToFileURL } from "url";
import { BrowserPool } from "./browser-pool.js";
import { Writable } from "stream";

// Configuration
const USE_STREAM_CAPTURE = process.env.USE_STREAM_CAPTURE !== "false";  // Default: true
const FRAME_FORMAT = (process.env.FRAME_FORMAT || "jpeg") as "jpeg" | "png";  // jpeg is faster
const FRAME_QUALITY = parseInt(process.env.FRAME_QUALITY || "90", 10);  // 90% quality for JPEG

interface FFmpegPipeResult {
  proc: ChildProcess;
  stdin: Writable;
  promise: Promise<void>;
}

/**
 * Spawn ffmpeg with stdin pipe for frame streaming.
 * 
 * EPIC B: This eliminates disk IO for frame files.
 */
function spawnFFmpegWithPipe(
  fps: number,
  width: number,
  height: number,
  outputPath: string,
  format: "webm" | "mp4",
  frameFormat: "jpeg" | "png" = "jpeg"
): FFmpegPipeResult {
  // Build ffmpeg args for image2pipe input
  const inputFormat = frameFormat === "jpeg" ? "mjpeg" : "png_pipe";
  
  const args: string[] = [
    "-y",
    "-f", inputFormat,
    "-framerate", String(fps),
    "-i", "pipe:0",  // Read from stdin
    "-s", `${width}x${height}`,
  ];
  
  // Add encoding options based on output format
  if (format === "webm") {
    args.push(
      "-c:v", "libvpx-vp9",
      "-pix_fmt", "yuva420p",
      "-b:v", "2M",
    );
  } else {
    args.push(
      "-c:v", "libx264",
      "-pix_fmt", "yuv420p",
      "-crf", "18",
      "-preset", "fast",
    );
  }
  
  args.push(outputPath);
  
  // Spawn ffmpeg with stdin pipe
  const proc = spawn("ffmpeg", args, {
    stdio: ["pipe", "ignore", "pipe"],
  });
  
  let stderr = "";
  proc.stderr?.on("data", (data) => {
    stderr += data.toString();
  });
  
  const promise = new Promise<void>((resolve, reject) => {
    proc.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`ffmpeg exited with code ${code}: ${stderr.slice(-1000)}`));
      }
    });
    
    proc.on("error", (err) => {
      reject(new Error(`ffmpeg spawn error: ${err.message}`));
    });
  });
  
  return { proc, stdin: proc.stdin as Writable, promise };
}

// Helper to run ffmpeg with spawn (no shell) for security - legacy file-based
function runFFmpeg(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    // Avoid buffering stdout (ffmpeg logs to stderr). Keep stderr for errors.
    const proc = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "pipe"] });
    
    let stderr = "";
    proc.stderr?.on("data", (data) => {
      stderr += data.toString();
    });
    
    proc.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`ffmpeg exited with code ${code}: ${stderr.slice(-500)}`));
      }
    });
    
    proc.on("error", (err) => {
      reject(new Error(`ffmpeg spawn error: ${err.message}`));
    });
  });
}

// Local dev defaults: use repo tmp/ so we don't require Docker-style /app paths.
// In Docker: keep /app paths (mounted /app exists).
const DEFAULT_OUTPUT_DIR = existsSync("/app")
  ? "/app/output"
  : path.resolve(process.cwd(), "..", "tmp", "render-service-out");
const DEFAULT_TMP_DIR = existsSync("/app")
  ? "/app/tmp"
  : path.resolve(process.cwd(), "..", "tmp", "render-service-tmp");

const OUTPUT_DIR = process.env.OUTPUT_DIR || DEFAULT_OUTPUT_DIR;
const TMP_DIR = process.env.TMP_DIR || DEFAULT_TMP_DIR;

// Global browser pool (initialized in index.ts)
let browserPool: BrowserPool | null = null;

export function setBrowserPool(pool: BrowserPool): void {
  browserPool = pool;
}

export function getBrowserPool(): BrowserPool | null {
  return browserPool;
}

// Types
export interface LayerPosition {
  x: number;
  y: number;
}

export interface LayerSize {
  width: number;
  height: number;
}

export interface TextStyle {
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: string;
  fontStyle?: string;
  color?: string;
  align?: string;
  verticalAlign?: string;
  lineHeight?: number;
}

export interface TextContent {
  baseContent: string;
  translations?: Record<string, string>;
  isTranslatable?: boolean;
  style?: TextStyle;
  overflow?: "shrinkFont" | "expandHeight" | "clip";
  minFontSize?: number;
}

export interface PlateContent {
  backgroundColor: string;
  backgroundOpacity?: number;
  borderRadius?: number;
  border?: { color: string; width: number };
  padding?: { top: number; right: number; bottom: number; left: number };
}

export interface ImageContent {
  assetId: string;
  assetUrl: string;
  fit?: "contain" | "cover" | "fill";
}

export interface AnimationTrigger {
  type: "time" | "start" | "end" | "marker" | "word";
  seconds?: number;
  offsetSeconds?: number;
  markerId?: string;
  charStart?: number;
  charEnd?: number;
  wordText?: string;
}

export interface AnimationConfig {
  type: string; // fadeIn, fadeOut, slideLeft, slideRight, slideUp, slideDown
  duration: number;
  delay?: number;
  easing?: string;
  trigger: AnimationTrigger;
}

export interface LayerAnimation {
  entrance?: AnimationConfig;
  exit?: AnimationConfig;
}

export interface SlideLayer {
  id: string;
  type: "text" | "image" | "plate";
  name: string;
  position: LayerPosition;
  size: LayerSize;
  rotation?: number;
  opacity?: number;
  visible?: boolean;
  locked?: boolean;
  zIndex: number;
  groupId?: string;
  text?: TextContent;
  plate?: PlateContent;
  image?: ImageContent;
  animation?: LayerAnimation;
}

export interface RenderRequest {
  slideId: string;
  slideImageUrl: string;
  layers: SlideLayer[];
  duration: number;
  width: number;
  height: number;
  fps: number;
  format: "webm" | "mp4";
  renderKey?: string;
  lang?: string;
}

export interface RenderResult {
  slideId: string;
  outputPath: string;
  duration: number;
  frames: number;
}

// Available fonts list - must match frontend PropertiesPanel.tsx options
export const AVAILABLE_FONTS = [
  "Inter",
  "Roboto", 
  "Open Sans",
  "Lato",
  "DejaVu Sans",
  "Liberation Sans",
  "Noto Sans",
] as const;

// Font preload CSS - helps Chromium cache fonts faster
const FONT_PRELOAD_CSS = `
  /* Preload common fonts with explicit @font-face declarations */
  @font-face {
    font-family: 'Inter';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Inter'), local('Inter Variable');
  }
  @font-face {
    font-family: 'Roboto';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Roboto'), local('Roboto Regular');
  }
  @font-face {
    font-family: 'Open Sans';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Open Sans'), local('OpenSans');
  }
  @font-face {
    font-family: 'Lato';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Lato'), local('Lato Regular');
  }
  @font-face {
    font-family: 'DejaVu Sans';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('DejaVu Sans'), local('DejaVuSans');
  }
  @font-face {
    font-family: 'Liberation Sans';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Liberation Sans'), local('LiberationSans');
  }
  @font-face {
    font-family: 'Noto Sans';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: local('Noto Sans'), local('NotoSans');
  }
`;

// SECURITY: Allowed base directories for file access (whitelist).
// This is the primary mitigation for the --disable-web-security Chromium flag.
//
// Architecture:
// 1. Backend converts asset URLs to filesystem paths (validated against DATA_DIR)
// 2. These paths are passed to render-service in the render request
// 3. normalizeSrc() below validates all paths against this whitelist
// 4. Chromium can only access files within these directories
//
// Default is strict: only the shared projects volume inside the container.
// Extend in dev via env: ALLOWED_BASE_PATHS="/data/projects,/some/other/base"
const DEFAULT_ALLOWED_BASE_PATHS = (() => {
  // In Docker we mount to /data/projects; in local dev we default to repo/data/projects
  if (existsSync("/data/projects")) return "/data/projects";
  return path.resolve(process.cwd(), "..", "data", "projects");
})();

const ALLOWED_BASE_PATHS = (process.env.ALLOWED_BASE_PATHS || DEFAULT_ALLOWED_BASE_PATHS)
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// SECURITY: Block external HTTP(S) URLs to prevent SSRF attacks.
// When enabled, only local filesystem paths are allowed for assets.
// Set BLOCK_EXTERNAL_URLS=true in production for maximum security.
// Default: true (secure by default)
const BLOCK_EXTERNAL_URLS = process.env.BLOCK_EXTERNAL_URLS !== "false";

// Cache resolved real paths of allowed base directories (computed once at startup)
let resolvedBasePaths: string[] | null = null;

async function getResolvedBasePaths(): Promise<string[]> {
  if (resolvedBasePaths !== null) {
    return resolvedBasePaths;
  }
  
  resolvedBasePaths = [];
  for (const basePath of ALLOWED_BASE_PATHS) {
    try {
      const realPath = await fs.realpath(basePath);
      resolvedBasePaths.push(realPath);
    } catch {
      // If base path doesn't exist, skip it (might not be mounted yet)
      // Keep original path as fallback
      resolvedBasePaths.push(basePath);
    }
  }
  return resolvedBasePaths;
}

// Synchronous version for use in HTML generation (paths already validated by async version)
function normalizeSrc(src: string): string {
  // Check if it's a URL
  try {
    const u = new URL(src);
    if (u.protocol === "http:" || u.protocol === "https:") {
      // SECURITY: Block external HTTP(S) URLs if configured (SSRF protection)
      if (BLOCK_EXTERNAL_URLS) {
        throw new Error(
          `Security: External URLs are blocked (SSRF protection). ` +
          `Use local filesystem paths instead. URL: ${src}`
        );
      }
      return u.toString();
    }
    // SECURITY: Reject file: URLs - they could access arbitrary local files
    if (u.protocol === "file:") {
      throw new Error(`Security: file: URLs are not allowed: ${src}`);
    }
  } catch (e) {
    // If it's our security error, rethrow
    if (e instanceof Error && e.message.startsWith("Security:")) {
      throw e;
    }
    // Otherwise, not a valid URL - treat as filesystem path
  }

  // Treat as filesystem path - resolve and validate against whitelist
  const abs = path.isAbsolute(src) ? src : path.resolve("/data/projects", src);
  
  // Normalize to resolve any ../ etc. (but does NOT resolve symlinks)
  const normalized = path.normalize(abs);
  
  // SECURITY: Validate that the resolved path is within allowed directories
  // Note: For symlink protection, use validatePathAsync() before calling this
  const isAllowed = ALLOWED_BASE_PATHS.some(basePath => 
    normalized.startsWith(basePath + path.sep) || normalized === basePath
  );
  
  if (!isAllowed) {
    throw new Error(`Security: Path not in allowed directories: ${normalized}`);
  }
  
  return pathToFileURL(normalized).toString();
}

// SECURITY: Async path validation with realpath() to prevent symlink bypass attacks
async function validatePathAsync(src: string): Promise<void> {
  // Skip URL validation (only for filesystem paths)
  try {
    const u = new URL(src);
    if (u.protocol === "http:" || u.protocol === "https:") {
      // SECURITY: Block external URLs if configured
      if (BLOCK_EXTERNAL_URLS) {
        throw new Error(
          `Security: External URLs are blocked (SSRF protection). ` +
          `Use local filesystem paths instead. URL: ${src}`
        );
      }
      return; // HTTP(S) URLs don't need path validation
    }
    if (u.protocol === "file:") {
      throw new Error(`Security: file: URLs are not allowed: ${src}`);
    }
  } catch (e) {
    if (e instanceof Error && e.message.startsWith("Security:")) {
      throw e;
    }
    // Not a URL, continue with path validation
  }

  // Resolve to absolute path
  const abs = path.isAbsolute(src) ? src : path.resolve("/data/projects", src);
  
  // SECURITY: Use realpath() to resolve symlinks and prevent bypass attacks
  let realPath: string;
  try {
    realPath = await fs.realpath(abs);
  } catch (e) {
    // If file doesn't exist, fall back to normalized path check
    // (file might be created later or this is a race condition)
    realPath = path.normalize(abs);
  }
  
  // Get resolved base paths (with symlinks resolved)
  const basePaths = await getResolvedBasePaths();
  
  // Validate that the real path is within allowed directories
  const isAllowed = basePaths.some(basePath => 
    realPath.startsWith(basePath + path.sep) || realPath === basePath
  );
  
  if (!isAllowed) {
    throw new Error(`Security: Path not in allowed directories (symlink check): ${realPath}`);
  }
}

// Generate HTML for slide with layers
function generateSlideHTML(request: RenderRequest): string {
  const { slideImageUrl, layers, width, height, duration } = request;
  const lang = request.lang || "en";
  const bgSrc = normalizeSrc(slideImageUrl);

  // Sort layers by zIndex
  const sortedLayers = [...layers]
    .filter((l) => l.visible !== false)
    .sort((a, b) => ((a as any).zIndex ?? 0) - ((b as any).zIndex ?? 0));

  // Generate CSS for animations
  const animationCSS = generateAnimationCSS(sortedLayers, duration);

  // Generate layer HTML
  const layersHTML = sortedLayers.map((layer) => generateLayerHTML(layer, lang)).join("\n");

  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    /* Font preload for faster rendering */
    ${FONT_PRELOAD_CSS}
    
    /* Supported fonts: Inter, Roboto, Open Sans, Lato, DejaVu Sans, Liberation Sans, Noto Sans */
    /* These fonts are installed in the Docker image and available via fontconfig */
    
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      width: ${width}px;
      height: ${height}px;
      overflow: hidden;
      background: #000;
      /* Set default font to Inter with fallbacks (including macOS Helvetica) */
      font-family: 'Inter', 'Roboto', 'Helvetica Neue', 'Helvetica', 'Arial', 'Open Sans', 'Lato', 'Noto Sans', 'Liberation Sans', 'DejaVu Sans', sans-serif;
    }
    
    .slide-container {
      position: relative;
      width: ${width}px;
      height: ${height}px;
    }
    
    .slide-background {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #000;
    }
    
    .layer {
      position: absolute;
      will-change: transform, opacity;
    }
    
    .layer-text {
      display: flex;
      word-wrap: break-word;
      white-space: pre-wrap;
    }
    
    .layer-plate {
      display: block;
    }
    
    .layer-image img {
      width: 100%;
      height: 100%;
    }
    
    .layer-image img.contain { object-fit: contain; }
    .layer-image img.cover { object-fit: cover; }
    .layer-image img.fill { object-fit: fill; }
    
    ${animationCSS}
  </style>
</head>
<body>
  <div class="slide-container">
    <img class="slide-background" src="${bgSrc}" />
    ${layersHTML}
  </div>
</body>
</html>
`;
}

// Generate CSS keyframes and animation rules
function generateAnimationCSS(layers: SlideLayer[], slideDuration: number): string {
  const rules: string[] = [];

  for (const layer of layers) {
    if (!layer.animation) continue;

    const layerClass = `layer-${layer.id}`;
    const { entrance, exit } = layer.animation;
    const baseOpacity = layer.opacity ?? 1;
    const rotation = layer.rotation || 0;

    // Calculate timings
    let entranceStart = 0;
    let entranceDuration = 0.3;
    let exitStart = slideDuration;
    let exitDuration = 0.3;

    if (entrance && entrance.type !== "none") {
      entranceStart = getTriggerTime(entrance.trigger, slideDuration) + (entrance.delay || 0);
      entranceDuration = entrance.duration || 0.3;
    }

    if (exit && exit.type !== "none") {
      exitStart = getTriggerTime(exit.trigger, slideDuration) + (exit.delay || 0);
      exitDuration = exit.duration || 0.3;
    }

    // Generate keyframes + apply BOTH entrance and exit animations on the SAME element.
    // We keep animations paused; the renderer drives timeline via Web Animations API (currentTime).
    const animationNames: string[] = [];
    const animationDurations: string[] = [];
    const animationEasings: string[] = [];
    const animationDelays: string[] = [];
    const animationFillModes: string[] = [];

    if (entrance && entrance.type !== "none") {
      const kf = `entrance-${layer.id}`;
      rules.push(generateKeyframes(kf, entrance.type, "entrance", rotation, baseOpacity));
      animationNames.push(kf);
      animationDurations.push(`${entranceDuration}s`);
      animationEasings.push(getEasing(entrance.easing));
      animationDelays.push(`${entranceStart}s`);
      animationFillModes.push("forwards");
    }

    if (exit && exit.type !== "none") {
      const kf = `exit-${layer.id}`;
      rules.push(generateKeyframes(kf, exit.type, "exit", rotation, baseOpacity));
      animationNames.push(kf);
      animationDurations.push(`${exitDuration}s`);
      animationEasings.push(getEasing(exit.easing));
      animationDelays.push(`${exitStart}s`);
      animationFillModes.push("forwards");
    }

    if (animationNames.length > 0) {
      const initialOpacity = entrance && entrance.type !== "none" ? 0 : baseOpacity;
      rules.push(`
        .${layerClass} {
          opacity: ${initialOpacity};
          animation-name: ${animationNames.join(", ")};
          animation-duration: ${animationDurations.join(", ")};
          animation-timing-function: ${animationEasings.join(", ")};
          animation-delay: ${animationDelays.join(", ")};
          animation-fill-mode: ${animationFillModes.join(", ")};
          animation-play-state: paused;
        }
      `);
    }
  }

  return rules.join("\n");
}

// Get trigger time in seconds
function getTriggerTime(trigger: AnimationTrigger, slideDuration: number): number {
  switch (trigger.type) {
    case "time":
      return trigger.seconds || 0;
    case "start":
      return trigger.offsetSeconds || 0;
    case "end":
      return slideDuration + (trigger.offsetSeconds || 0);
    case "marker":
    case "word":
      // These should be resolved to time before rendering
      return trigger.seconds || 0;
    default:
      return 0;
  }
}

// Generate CSS keyframes
function generateKeyframes(
  name: string,
  animationType: string,
  phase: "entrance" | "exit",
  rotationDeg: number,
  baseOpacity: number
): string {
  const isEntrance = phase === "entrance";
  const rot = rotationDeg ? ` rotate(${rotationDeg}deg)` : "";
  const fromOpacity = isEntrance ? 0 : baseOpacity;
  const toOpacity = isEntrance ? baseOpacity : 0;

  switch (animationType) {
    case "fadeIn":
    case "fadeOut":
      return `
        @keyframes ${name} {
          from { opacity: ${fromOpacity}; }
          to { opacity: ${toOpacity}; }
        }
      `;

    case "slideLeft":
      return `
        @keyframes ${name} {
          from { 
            opacity: ${fromOpacity}; 
            transform: translateX(${isEntrance ? "100px" : "0"})${rot}; 
          }
          to { 
            opacity: ${toOpacity}; 
            transform: translateX(${isEntrance ? "0" : "-100px"})${rot}; 
          }
        }
      `;

    case "slideRight":
      return `
        @keyframes ${name} {
          from { 
            opacity: ${fromOpacity}; 
            transform: translateX(${isEntrance ? "-100px" : "0"})${rot}; 
          }
          to { 
            opacity: ${toOpacity}; 
            transform: translateX(${isEntrance ? "0" : "100px"})${rot}; 
          }
        }
      `;

    case "slideUp":
      return `
        @keyframes ${name} {
          from { 
            opacity: ${fromOpacity}; 
            transform: translateY(${isEntrance ? "50px" : "0"})${rot}; 
          }
          to { 
            opacity: ${toOpacity}; 
            transform: translateY(${isEntrance ? "0" : "-50px"})${rot}; 
          }
        }
      `;

    case "slideDown":
      return `
        @keyframes ${name} {
          from { 
            opacity: ${fromOpacity}; 
            transform: translateY(${isEntrance ? "-50px" : "0"})${rot}; 
          }
          to { 
            opacity: ${toOpacity}; 
            transform: translateY(${isEntrance ? "0" : "50px"})${rot}; 
          }
        }
      `;

    default:
      return `
        @keyframes ${name} {
          from { opacity: ${fromOpacity}; }
          to { opacity: ${toOpacity}; }
        }
      `;
  }
}

// Get CSS easing function
function getEasing(easing?: string): string {
  switch (easing) {
    case "linear":
      return "linear";
    case "easeIn":
      return "ease-in";
    case "easeOut":
      return "ease-out";
    case "easeInOut":
      return "ease-in-out";
    default:
      return "ease-out";
  }
}

// Generate HTML for a single layer
function generateLayerHTML(layer: SlideLayer, lang: string): string {
  const { id, type, position, size, rotation, opacity, animation } = layer;
  const layerClass = `layer layer-${id}`;
  
  // Base styles
  const styles: string[] = [
    `left: ${position.x}px`,
    `top: ${position.y}px`,
    `width: ${size.width}px`,
    `height: ${size.height}px`,
  ];

  const hasAnimation =
    (animation?.entrance && animation.entrance.type && animation.entrance.type !== "none") ||
    (animation?.exit && animation.exit.type && animation.exit.type !== "none");

  if (rotation) styles.push(`transform: rotate(${rotation}deg)`);
  // IMPORTANT: If this layer has CSS animations, do NOT set inline opacity.
  // Inline styles would override the "hidden before entrance" state.
  if (!hasAnimation) {
    if (opacity !== undefined && opacity !== 1) styles.push(`opacity: ${opacity}`);
  }

  let content = "";

  switch (type) {
    case "text":
      content = generateTextLayerHTML(layer, lang);
      break;
    case "plate":
      content = generatePlateLayerHTML(layer);
      break;
    case "image":
      content = generateImageLayerHTML(layer);
      break;
  }

  return `<div class="${layerClass}" style="${styles.join("; ")}">${content}</div>`;
}

// Generate text layer content
function generateTextLayerHTML(layer: SlideLayer, lang: string): string {
  if (!layer.text) return "";

  const { baseContent, translations, style, overflow, minFontSize } = layer.text;
  // DEBUG: Log text style
  console.log("Text layer style:", JSON.stringify(style));
  const text = translations?.[lang] || baseContent;
  // Default to expandHeight so user-selected fontSize is preserved (no forced shrinking).
  // shrinkFont can still be enabled explicitly per-layer.
  const overflowMode = overflow || "expandHeight";
  const minFont = minFontSize || 12;
  const baseFontSize = style?.fontSize || 24;

  // Font fallback chain for common fonts (including macOS Helvetica)
  // Use single quotes for font names to avoid breaking HTML style="" attribute
  const fontFamily = style?.fontFamily || "Inter";
  const fontFallbacks = `'${fontFamily}', 'Inter', 'Roboto', 'Helvetica Neue', 'Helvetica', 'Arial', 'Open Sans', 'Lato', 'Noto Sans', 'Liberation Sans', 'DejaVu Sans', sans-serif`;
  
  const textStyles: string[] = [
    `font-family: ${fontFallbacks}`,
    `font-size: ${baseFontSize}px`,
    `font-weight: ${style?.fontWeight || "normal"}`,
    `font-style: ${style?.fontStyle || "normal"}`,
    `color: ${style?.color || "#000000"}`,
    `text-align: ${style?.align || "left"}`,
    `line-height: ${style?.lineHeight || 1.4}`,
    "width: 100%",
    "height: 100%",
  ];

  // Vertical alignment
  if (style?.verticalAlign === "middle") {
    textStyles.push("display: flex", "align-items: center");
  } else if (style?.verticalAlign === "bottom") {
    textStyles.push("display: flex", "align-items: flex-end");
  }

  // Overflow handling
  if (overflowMode === "clip") {
    textStyles.push("overflow: hidden");
  } else if (overflowMode === "shrinkFont") {
    // For shrinkFont, we apply it in renderSlide() AFTER fonts are loaded (so measurements are correct).
    textStyles.push("overflow: hidden");
  }
  // For "expandHeight", no special handling - let text overflow naturally

  // Add data attributes for shrinkFont handling via JS
  const dataAttrs = overflowMode === "shrinkFont" 
    ? `data-overflow="shrinkFont" data-base-font="${baseFontSize}" data-min-font="${minFont}"`
    : "";

  return `<div class="layer-text" ${dataAttrs} style="${textStyles.join("; ")}">${escapeHTML(text)}</div>`;
}

// Generate plate layer content
function generatePlateLayerHTML(layer: SlideLayer): string {
  if (!layer.plate) return "";

  const { backgroundColor, backgroundOpacity, borderRadius, border, padding } = layer.plate;

  const styles: string[] = [
    `background-color: ${backgroundColor}`,
    `opacity: ${backgroundOpacity ?? 1}`,
    `border-radius: ${borderRadius || 0}px`,
    "width: 100%",
    "height: 100%",
  ];

  if (border) {
    styles.push(`border: ${border.width}px solid ${border.color}`);
  }

  if (padding) {
    styles.push(`padding: ${padding.top}px ${padding.right}px ${padding.bottom}px ${padding.left}px`);
  }

  return `<div class="layer-plate" style="${styles.join("; ")}"></div>`;
}

// Generate image layer content
function generateImageLayerHTML(layer: SlideLayer): string {
  if (!layer.image) return "";

  const { assetUrl, fit } = layer.image;
  const fitClass = fit || "contain";
  const src = normalizeSrc(assetUrl);

  return `<div class="layer-image"><img src="${src}" class="${fitClass}" /></div>`;
}

// Escape HTML
function escapeHTML(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Main render function
export async function renderSlide(
  request: RenderRequest,
  logger: Logger
): Promise<RenderResult> {
  const { slideId, duration, width, height, fps, format, layers } = request;
  
  // Validate duration to prevent ffmpeg failures with empty frame sequences
  if (duration <= 0) {
    throw new Error(`Invalid duration: ${duration}. Duration must be > 0`);
  }
  
  // Ensure at least 1 frame even for very short durations
  const frameCount = Math.max(1, Math.ceil(duration * fps));

  // SECURITY: Validate all paths with realpath() to prevent symlink bypass attacks
  await validatePathAsync(request.slideImageUrl);
  for (const layer of layers) {
    if (layer.type === "image" && layer.image?.assetUrl) {
      await validatePathAsync(layer.image.assetUrl);
    }
  }

  const sessionId = uuidv4();
  const framesDir = path.join(TMP_DIR, sessionId);
  const outputFileName = `${slideId}-${sessionId}.${format}`;
  const outputPath = path.join(OUTPUT_DIR, outputFileName);

  await fs.mkdir(framesDir, { recursive: true });
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  // Acquire page from pool (or create one if pool not initialized)
  let page: Page;
  let usingPool = false;
  
  if (browserPool) {
    page = await browserPool.acquire();
    usingPool = true;
  } else {
    // Fallback: create browser on-demand (slower, used in tests)
    const puppeteer = await import("puppeteer");
    const protocolTimeoutMs = parseInt(process.env.PUPPETEER_PROTOCOL_TIMEOUT_MS || "600000", 10);
    const browser = await puppeteer.default.launch({
      headless: true,
      protocolTimeout: protocolTimeoutMs,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });
    page = await browser.newPage();
  }

  try {
    // Set viewport (pool pages already have viewport, but re-set in case dimensions differ)
    await page.setViewport({ width, height, deviceScaleFactor: 1 });

    // Generate and load HTML
    const html = generateSlideHTML(request);
    // IMPORTANT (local dev): Chromium will NOT load file:// images when the page is about:blank (page.setContent).
    // To allow local slide/background images, write HTML to a temp file and navigate via file://.
    // In Docker this also works and keeps behavior consistent across environments.
    const htmlFilePath = path.join(framesDir, "slide.html");
    await fs.writeFile(htmlFilePath, html, "utf8");
    
    // DEBUG: Save HTML for inspection
    const debugHtmlPath = `/tmp/debug-slide-${slideId}.html`;
    await fs.writeFile(debugHtmlPath, html, "utf8");
    logger.info("Debug HTML saved", { path: debugHtmlPath });
    
    // DEBUG: Log the slideImageUrl and layers for debugging
    logger.info("Rendering slide", { slideId, slideImageUrl: request.slideImageUrl });
    logger.info("Layers data", { layers: JSON.stringify(layers, null, 2) });
    // Use domcontentloaded instead of networkidle0 for faster loading
    // (we explicitly wait for images below)
    await page.goto(pathToFileURL(htmlFilePath).toString(), { waitUntil: "domcontentloaded", timeout: 30000 });

    // Ensure images are loaded before capture (background + any asset images).
    await page.evaluate(async () => {
      const imgs = Array.from(document.images) as HTMLImageElement[];
      await Promise.all(
        imgs.map(async (img) => {
          try {
            if (img.complete && img.naturalWidth > 0) return;
            if (typeof (img as any).decode === "function") {
              await (img as any).decode().catch(() => {});
              return;
            }
            await new Promise<void>((resolve) => {
              img.addEventListener("load", () => resolve(), { once: true });
              img.addEventListener("error", () => resolve(), { once: true });
            });
          } catch {
            // ignore
          }
        })
      );

      // Fail fast if the slide background didn't load (prevents silently producing black frames).
      const bg = document.querySelector(".slide-background") as HTMLImageElement | null;
      if (bg && bg.naturalWidth === 0) {
        throw new Error(`Background image failed to load: ${bg.getAttribute("src") || ""}`);
      }

      // Force a style/layout flush
      void document.body.getBoundingClientRect();
    });

    // Ensure fonts are ready (prevents fallback fonts on early frames)
    await page.evaluate(async () => {
      const fontSet = (document as any).fonts;
      if (fontSet && typeof fontSet.ready?.then === "function") {
        try {
          // Proactively load common fonts
          await Promise.allSettled([
            fontSet.load('12px "Inter"'),
            fontSet.load('12px "Roboto"'),
            fontSet.load('12px "Open Sans"'),
            fontSet.load('12px "Lato"'),
          ]);
        } catch {
          // ignore
        }
        await fontSet.ready;
      }
    });

    // Apply shrinkFont overflow after fonts are ready (important for correct measurements)
    await page.evaluate(() => {
      const elements = document.querySelectorAll('[data-overflow="shrinkFont"]');
      elements.forEach((el) => {
        const hEl = el as HTMLElement;
        const baseFont = parseFloat(hEl.dataset.baseFont || "") || 24;
        const minFont = parseFloat(hEl.dataset.minFont || "") || 12;
        const container = hEl.parentElement as HTMLElement | null;
        if (!container) return;

        const maxHeight = container.offsetHeight;
        let lo = minFont;
        let hi = baseFont;

        // Binary search for max font size that fits in height.
        while (hi - lo > 0.5) {
          const mid = (lo + hi) / 2;
          hEl.style.fontSize = `${mid}px`;
          if (hEl.scrollHeight <= maxHeight) {
            lo = mid;
          } else {
            hi = mid;
          }
        }
        hEl.style.fontSize = `${lo}px`;
      });
    });

    // Pause all animations once; we'll drive timeline deterministically per frame.
    // EPIC B: Expose __setTimelineTime for deterministic timeline control
    await page.evaluate(() => {
      const anims = document.getAnimations();
      for (const a of anims) {
        a.pause();
      }
      // Store for reuse
      (window as any).__anims = anims;
      
      // EPIC B: Global function for deterministic timeline control
      (window as any).__setTimelineTime = (timeMs: number) => {
        const storedAnims: Animation[] = (window as any).__anims || document.getAnimations();
        for (const a of storedAnims) {
          a.currentTime = timeMs;
        }
        // Force style/layout flush
        void document.body.getBoundingClientRect();
      };
    });

    logger.info("Capturing frames", { 
      count: frameCount, 
      fps, 
      mode: USE_STREAM_CAPTURE ? "stream" : "file",
      format: FRAME_FORMAT 
    });

    // === EPIC B: Stream capture with ffmpeg pipe ===
    if (USE_STREAM_CAPTURE) {
      // Spawn ffmpeg with stdin pipe
      const { stdin, promise: ffmpegPromise } = spawnFFmpegWithPipe(
        fps, width, height, outputPath, format, FRAME_FORMAT
      );
      
      let framesWritten = 0;
      
      try {
        for (let i = 0; i < frameCount; i++) {
          const currentTime = i / fps;

          // Set timeline position using deterministic control
          await page.evaluate((timeMs) => {
            (window as any).__setTimelineTime(timeMs);
          }, currentTime * 1000);

          // Capture screenshot to buffer (no disk IO!)
          const buffer = await page.screenshot({ 
            type: FRAME_FORMAT, 
            quality: FRAME_FORMAT === "jpeg" ? FRAME_QUALITY : undefined,
            encoding: "binary"
          }) as Buffer;

          // Write frame to ffmpeg stdin
          const canWrite = stdin.write(buffer);
          framesWritten++;
          
          // Handle backpressure - wait for drain if buffer is full
          if (!canWrite) {
            await new Promise<void>((resolve) => stdin.once("drain", resolve));
          }

          // Progress logging every 10%
          if (i % Math.ceil(frameCount / 10) === 0) {
            logger.debug("Frame progress", { 
              frame: i, 
              total: frameCount, 
              percent: Math.round((i / frameCount) * 100) 
            });
          }
        }
        
        // Close stdin to signal end of input
        stdin.end();
        
        // Wait for ffmpeg to finish encoding
        await ffmpegPromise;
        
        logger.info("Video encoded (stream mode)", { 
          outputPath, 
          framesWritten,
          format: FRAME_FORMAT
        });
        
      } catch (error) {
        // Ensure stdin is closed on error
        try { stdin.end(); } catch { /* ignore */ }
        throw error;
      }
    } else {
      // === Legacy file-based capture (fallback) ===
      for (let i = 0; i < frameCount; i++) {
        const currentTime = i / fps;

        // Set global timeline position (ms) for all animations.
        await page.evaluate((timeMs) => {
          (window as any).__setTimelineTime(timeMs);
        }, currentTime * 1000);

        // Capture screenshot to file
        const framePath = path.join(framesDir, `frame-${String(i).padStart(6, "0")}.png`);
        await page.screenshot({ path: framePath, type: "png" });

        // Progress logging every 10%
        if (i % Math.ceil(frameCount / 10) === 0) {
          logger.debug("Frame progress", { frame: i, total: frameCount, percent: Math.round((i / frameCount) * 100) });
        }
      }

      logger.info("Encoding video with FFmpeg (file mode)");

      // Encode frames to video using FFmpeg
      // SECURITY: Use spawn with array args instead of shell command to prevent injection
      const inputPattern = `${framesDir}/frame-%06d.png`;
      const ffmpegArgs = format === "webm"
        ? ["-y", "-framerate", String(fps), "-i", inputPattern, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "2M", outputPath]
        : ["-y", "-framerate", String(fps), "-i", inputPattern, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast", outputPath];

      await runFFmpeg(ffmpegArgs);

      logger.info("Video encoded (file mode)", { outputPath });
    }

    return {
      slideId,
      outputPath: outputFileName,
      duration,
      frames: frameCount,
    };
  } finally {
    // Release page back to pool or close if not using pool
    if (usingPool && browserPool) {
      try {
        await browserPool.release(page);
      } catch (e) {
        logger.warn("Failed to release page back to pool", {
          slideId,
          error: e instanceof Error ? e.message : String(e),
        });
      }
    } else {
      const browser = page.browser();
      await page.close();
      await browser.close();
    }
    
    // EPIC B: Only cleanup frames directory if using file mode
    // In stream mode, frames are never written to disk
    if (!USE_STREAM_CAPTURE) {
      // SECURITY FIX: Wrap cleanup in try/catch to prevent masking render errors
      try {
        await fs.rm(framesDir, { recursive: true, force: true });
      } catch (cleanupError) {
        logger.warn("Failed to cleanup frames directory", {
          slideId,
          framesDir,
          error: cleanupError instanceof Error ? cleanupError.message : String(cleanupError),
        });
      }
    }
  }
}

// === PREVIEW RENDERING ===

export interface PreviewRequest {
  slideId: string;
  slideImageUrl: string;
  layers: SlideLayer[];
  width: number;
  height: number;
  lang?: string;
}

export interface PreviewResult {
  slideId: string;
  outputPath: string;
}

/**
 * Render a single PNG preview frame with all layers applied.
 * This is used for generating slide thumbnails after Canvas Editor save.
 */
export async function renderPreview(
  request: PreviewRequest,
  logger: Logger
): Promise<PreviewResult> {
  const { slideId, width, height, layers } = request;

  // Validate slideImageUrl path
  await validatePathAsync(request.slideImageUrl);
  for (const layer of layers) {
    if (layer.type === "image" && layer.image?.assetUrl) {
      await validatePathAsync(layer.image.assetUrl);
    }
  }

  const sessionId = uuidv4();
  const outputFileName = `preview-${slideId}.png`;
  const outputPath = path.join(OUTPUT_DIR, outputFileName);

  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  // Acquire page from pool
  let page: Page;
  let usingPool = false;

  if (browserPool) {
    page = await browserPool.acquire();
    usingPool = true;
  } else {
    const puppeteer = await import("puppeteer");
    const browser = await puppeteer.default.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });
    page = await browser.newPage();
  }

  try {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });

    // Generate HTML without animations (static preview)
    const html = generatePreviewHTML(request);
    
    // Write to temp file for local file access
    const tmpDir = path.join(TMP_DIR, sessionId);
    await fs.mkdir(tmpDir, { recursive: true });
    const htmlFilePath = path.join(tmpDir, "preview.html");
    await fs.writeFile(htmlFilePath, html, "utf8");

    await page.goto(pathToFileURL(htmlFilePath).toString(), { waitUntil: "domcontentloaded", timeout: 30000 });

    // Wait for images to load
    await page.evaluate(async () => {
      const imgs = Array.from(document.images) as HTMLImageElement[];
      await Promise.all(
        imgs.map(async (img) => {
          try {
            if (img.complete && img.naturalWidth > 0) return;
            if (typeof (img as any).decode === "function") {
              await (img as any).decode().catch(() => {});
              return;
            }
            await new Promise<void>((resolve) => {
              img.addEventListener("load", () => resolve(), { once: true });
              img.addEventListener("error", () => resolve(), { once: true });
            });
          } catch {
            // ignore
          }
        })
      );
      void document.body.getBoundingClientRect();
    });

    // Wait for fonts
    await page.evaluate(async () => {
      const fontSet = (document as any).fonts;
      if (fontSet && typeof fontSet.ready?.then === "function") {
        await fontSet.ready;
      }
    });

    // Apply shrinkFont if needed
    await page.evaluate(() => {
      const elements = document.querySelectorAll('[data-overflow="shrinkFont"]');
      elements.forEach((el) => {
        const hEl = el as HTMLElement;
        const baseFont = parseFloat(hEl.dataset.baseFont || "") || 24;
        const minFont = parseFloat(hEl.dataset.minFont || "") || 12;
        const container = hEl.parentElement as HTMLElement | null;
        if (!container) return;

        const maxHeight = container.offsetHeight;
        let lo = minFont;
        let hi = baseFont;

        while (hi - lo > 0.5) {
          const mid = (lo + hi) / 2;
          hEl.style.fontSize = `${mid}px`;
          if (hEl.scrollHeight <= maxHeight) {
            lo = mid;
          } else {
            hi = mid;
          }
        }
        hEl.style.fontSize = `${lo}px`;
      });
    });

    // Take screenshot
    await page.screenshot({
      path: outputPath,
      type: "png",
      fullPage: false,
    });

    // Cleanup temp directory
    await fs.rm(tmpDir, { recursive: true, force: true });

    logger.info("Preview rendered", { slideId, outputPath });

    return {
      slideId,
      outputPath,
    };
  } finally {
    if (usingPool && browserPool) {
      try {
        await browserPool.release(page);
      } catch (e) {
        logger.warn("Failed to release page back to pool", { error: String(e) });
      }
    } else {
      const browser = page.browser();
      await page.close();
      await browser.close();
    }
  }
}

/**
 * Generate static HTML for preview (no animations)
 */
function generatePreviewHTML(request: PreviewRequest): string {
  const { width, height, layers } = request;
  const lang = request.lang || "en";
  const bgSrc = normalizeSrc(request.slideImageUrl);

  // Sort layers by zIndex
  const sortedLayers = [...layers]
    .filter(l => l.visible !== false)
    .sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));

  // Generate layers HTML (without animation classes)
  const layersHTML = sortedLayers.map(layer => generatePreviewLayerHTML(layer, lang)).join("\n");

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      width: ${width}px;
      height: ${height}px;
      overflow: hidden;
      background: #000;
      font-family: 'Inter', 'Roboto', 'Helvetica Neue', 'Helvetica', 'Arial', sans-serif;
    }
    
    .slide-container {
      position: relative;
      width: ${width}px;
      height: ${height}px;
    }
    
    .slide-background {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    .layer {
      position: absolute;
    }
    
    .layer-text {
      display: flex;
      word-wrap: break-word;
      white-space: pre-wrap;
    }
    
    .layer-plate {
      display: block;
    }
    
    .layer-image img {
      width: 100%;
      height: 100%;
    }
    
    .layer-image img.contain { object-fit: contain; }
    .layer-image img.cover { object-fit: cover; }
    .layer-image img.fill { object-fit: fill; }
  </style>
</head>
<body>
  <div class="slide-container">
    <img class="slide-background" src="${bgSrc}" />
    ${layersHTML}
  </div>
</body>
</html>`;
}

/**
 * Generate layer HTML for preview (no animations, all layers visible)
 */
function generatePreviewLayerHTML(layer: SlideLayer, lang: string): string {
  const { id, type, position, size, rotation, opacity } = layer;
  const layerClass = `layer layer-${id}`;

  const styles: string[] = [
    `left: ${position.x}px`,
    `top: ${position.y}px`,
    `width: ${size.width}px`,
    `height: ${size.height}px`,
  ];

  if (rotation) styles.push(`transform: rotate(${rotation}deg)`);
  if (opacity !== undefined && opacity !== 1) styles.push(`opacity: ${opacity}`);

  let content = "";

  switch (type) {
    case "text":
      content = generateTextLayerHTML(layer, lang);
      break;
    case "plate":
      content = generatePlateLayerHTML(layer);
      break;
    case "image":
      content = generateImageLayerHTML(layer);
      break;
  }

  return `<div class="${layerClass}" style="${styles.join("; ")}">${content}</div>`;
}

// Cleanup on exit (handled by browser pool in index.ts)

