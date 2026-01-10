import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { EventEmitter } from "events";
import { Writable } from "stream";
import fs from "fs/promises";
import path from "path";

// Mock ffmpeg spawn so tests don't require ffmpeg on PATH
const spawnMock = vi.fn();
vi.mock("child_process", () => ({
  spawn: spawnMock,
}));

function makeFakeFFmpegProcess(opts?: { autoClose?: boolean; onStdinWrite?: (b: Buffer) => void }) {
  const proc = new EventEmitter() as any;
  proc.stderr = new EventEmitter();

  const chunks: Buffer[] = [];
  const stdin = new Writable({
    write(chunk, _enc, cb) {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as any);
      chunks.push(buf);
      opts?.onStdinWrite?.(buf);
      cb();
    },
  });

  // When stdin ends, simulate ffmpeg finishing successfully.
  const origEnd = stdin.end.bind(stdin);
  stdin.end = ((...args: any[]) => {
    origEnd(...args);
    if (opts?.autoClose !== false) {
      queueMicrotask(() => proc.emit("close", 0));
    }
  }) as any;

  proc.stdin = stdin;
  return { proc, chunks };
}

describe("renderSlide (EPIC B stream capture)", () => {
  const tmpRoot = path.join("/tmp", `render-service-test-${Date.now()}`);
  const assetsDir = path.join(tmpRoot, "assets");
  const outDir = path.join(tmpRoot, "out");
  const tmpDir = path.join(tmpRoot, "tmp");
  const slidePath = path.join(assetsDir, "slide.png");

  beforeEach(async () => {
    vi.resetModules();
    spawnMock.mockReset();

    process.env.ALLOWED_BASE_PATHS = assetsDir;
    process.env.OUTPUT_DIR = outDir;
    process.env.TMP_DIR = tmpDir;
    process.env.BLOCK_EXTERNAL_URLS = "true";
    process.env.USE_STREAM_CAPTURE = "true";
    process.env.FRAME_FORMAT = "jpeg";
    process.env.FRAME_QUALITY = "90";

    await fs.mkdir(assetsDir, { recursive: true });
    await fs.mkdir(outDir, { recursive: true });
    await fs.mkdir(tmpDir, { recursive: true });
    await fs.writeFile(slidePath, "x");
  });

  afterEach(async () => {
    // Best-effort cleanup
    try {
      await fs.rm(tmpRoot, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("pipes in-memory frames to ffmpeg (no frame files)", async () => {
    const { proc, chunks } = makeFakeFFmpegProcess();
    spawnMock.mockImplementation(() => proc);

    const { renderSlide, setBrowserPool } = await import("./renderer.js");

    const screenshotMock = vi.fn().mockResolvedValue(Buffer.from([1, 2, 3]));
    const page = {
      setViewport: vi.fn().mockResolvedValue(undefined),
      setContent: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockResolvedValue(undefined),
      screenshot: screenshotMock,
    } as any;

    const pool = {
      acquire: vi.fn().mockResolvedValue(page),
      release: vi.fn().mockResolvedValue(undefined),
    } as any;
    setBrowserPool(pool);

    const mockLogger = {
      info: vi.fn(),
      debug: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    } as any;

    const result = await renderSlide(
      {
        slideId: "00000000-0000-0000-0000-000000000001",
        slideImageUrl: slidePath,
        layers: [],
        duration: 0.05, // 1 frame @ 30fps
        width: 1920,
        height: 1080,
        fps: 30,
        format: "mp4",
      },
      mockLogger
    );

    // ffmpeg called with pipe input
    expect(spawnMock).toHaveBeenCalled();
    const args = spawnMock.mock.calls[0][1] as string[];
    expect(args).toContain("pipe:0");
    expect(args).toContain("mjpeg");

    // Screenshot captured in-memory (no path)
    expect(screenshotMock).toHaveBeenCalled();
    const shotArgs = screenshotMock.mock.calls[0][0] as any;
    expect(shotArgs.path).toBeUndefined();
    expect(shotArgs.type).toBe("jpeg");
    expect(shotArgs.encoding).toBe("binary");

    // At least one frame was written to ffmpeg stdin
    expect(chunks.length).toBeGreaterThan(0);

    expect(result).toHaveProperty("outputPath");
  });

  it("blocks external HTTP(S) URLs by default (SSRF protection)", async () => {
    // Default is BLOCK_EXTERNAL_URLS=true (set in beforeEach)
    const { renderSlide } = await import("./renderer.js");
    const mockLogger = {
      info: vi.fn(),
      debug: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    } as any;

    await expect(
      renderSlide(
        {
          slideId: "00000000-0000-0000-0000-000000000002",
          slideImageUrl: "https://example.com/slide.png",
          layers: [],
          duration: 0.1,
          width: 1920,
          height: 1080,
          fps: 30,
          format: "mp4",
        },
        mockLogger
      )
    ).rejects.toThrow(/external urls are blocked/i);
  });

  it("allows external HTTP(S) URLs when explicitly enabled", async () => {
    // Allow external URLs for this test
    process.env.BLOCK_EXTERNAL_URLS = "false";
    vi.resetModules();

    const { proc } = makeFakeFFmpegProcess();
    spawnMock.mockImplementation(() => proc);

    const { renderSlide, setBrowserPool } = await import("./renderer.js");

    const screenshotMock = vi.fn().mockResolvedValue(Buffer.from([1, 2, 3]));
    const page = {
      setViewport: vi.fn().mockResolvedValue(undefined),
      setContent: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockResolvedValue(undefined),
      screenshot: screenshotMock,
    } as any;

    const pool = {
      acquire: vi.fn().mockResolvedValue(page),
      release: vi.fn().mockResolvedValue(undefined),
    } as any;
    setBrowserPool(pool);

    const mockLogger = {
      info: vi.fn(),
      debug: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    } as any;

    const result = await renderSlide(
      {
        slideId: "00000000-0000-0000-0000-000000000003",
        slideImageUrl: "https://example.com/slide.png",
        layers: [],
        duration: 0.05, // 1 frame
        width: 1920,
        height: 1080,
        fps: 30,
        format: "mp4",
      },
      mockLogger
    );

    expect(result).toHaveProperty("outputPath");
  });
});


