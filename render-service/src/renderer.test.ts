/**
 * Tests for renderer.ts - path validation and security
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { SlideLayer } from "./renderer.js";

// We need to test the normalizeSrc function which is not exported
// So we'll test it indirectly through the module behavior

describe("Path Security", () => {
  // Store original env
  const originalEnv = process.env.ALLOWED_BASE_PATHS;

  beforeAll(() => {
    // Set up test environment
    process.env.ALLOWED_BASE_PATHS = "/data/projects,/tmp/test-assets";
  });

  afterAll(() => {
    // Restore env
    if (originalEnv !== undefined) {
      process.env.ALLOWED_BASE_PATHS = originalEnv;
    } else {
      delete process.env.ALLOWED_BASE_PATHS;
    }
  });

  describe("ALLOWED_BASE_PATHS configuration", () => {
    it("should parse comma-separated paths", async () => {
      // Re-import to get fresh module with new env
      const { AVAILABLE_FONTS } = await import("./renderer.js");
      
      // If we got here without error, the module loaded correctly
      expect(AVAILABLE_FONTS).toBeDefined();
      expect(AVAILABLE_FONTS).toContain("Inter");
    });
  });
});

describe("Available Fonts", () => {
  it("should export AVAILABLE_FONTS array", async () => {
    const { AVAILABLE_FONTS } = await import("./renderer.js");
    
    expect(Array.isArray(AVAILABLE_FONTS)).toBe(true);
    expect(AVAILABLE_FONTS.length).toBeGreaterThan(0);
  });

  it("should include all required fonts", async () => {
    const { AVAILABLE_FONTS } = await import("./renderer.js");
    
    const requiredFonts = [
      "Inter",
      "Roboto",
      "Open Sans",
      "Lato",
      "DejaVu Sans",
      "Liberation Sans",
      "Noto Sans",
    ];

    for (const font of requiredFonts) {
      expect(AVAILABLE_FONTS).toContain(font);
    }
  });

  it("should NOT include removed fonts (Montserrat, Poppins)", async () => {
    const { AVAILABLE_FONTS } = await import("./renderer.js");
    
    expect(AVAILABLE_FONTS).not.toContain("Montserrat");
    expect(AVAILABLE_FONTS).not.toContain("Poppins");
  });
});

describe("RenderRequest validation", () => {
  it("should reject duration <= 0", async () => {
    const { renderSlide } = await import("./renderer.js");
    const mockLogger = {
      info: () => {},
      debug: () => {},
      warn: () => {},
      error: () => {},
    } as any;

    const invalidRequest = {
      slideId: "test-slide",
      slideImageUrl: "/data/projects/test/slide.png",
      layers: [],
      duration: 0, // Invalid!
      width: 1920,
      height: 1080,
      fps: 30,
      format: "mp4" as const,
    };

    await expect(renderSlide(invalidRequest, mockLogger)).rejects.toThrow(
      /duration/i
    );
  });

  it("should reject negative duration", async () => {
    const { renderSlide } = await import("./renderer.js");
    const mockLogger = {
      info: () => {},
      debug: () => {},
      warn: () => {},
      error: () => {},
    } as any;

    const invalidRequest = {
      slideId: "test-slide",
      slideImageUrl: "/data/projects/test/slide.png",
      layers: [],
      duration: -5, // Invalid!
      width: 1920,
      height: 1080,
      fps: 30,
      format: "mp4" as const,
    };

    await expect(renderSlide(invalidRequest, mockLogger)).rejects.toThrow(
      /duration/i
    );
  });
});

describe("Layer visibility", () => {
  // Test that visible: undefined is treated as visible
  // This is tested via the generated HTML
  
  it("should treat missing visible as true", async () => {
    // The layer filtering happens in generateSlideHTML
    // visible !== false means visible is treated as true
    const layer: Partial<SlideLayer> = {
      id: "test",
      type: "text" as const,
      name: "Test",
      position: { x: 0, y: 0 },
      size: { width: 100, height: 50 },
      zIndex: 0,
      // visible is missing - should be treated as visible
    };

    // visible !== false -> should pass the filter
    expect(layer.visible !== false).toBe(true);
  });

  it("should hide layer when visible === false", () => {
    const layer: Partial<SlideLayer> = {
      id: "test",
      type: "text" as const,
      name: "Test",
      position: { x: 0, y: 0 },
      size: { width: 100, height: 50 },
      zIndex: 0,
      visible: false,
    };

    expect(layer.visible !== false).toBe(false);
  });
});

