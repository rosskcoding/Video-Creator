/**
 * Tests for PropertiesPanel - font list synchronization
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PropertiesPanel } from "./PropertiesPanel";
import type { SlideLayer } from "@/lib/api";

// The font list must match render-service/src/renderer.ts AVAILABLE_FONTS
const EXPECTED_FONTS = [
  "Inter",
  "Roboto",
  "Open Sans",
  "Lato",
  "DejaVu Sans",
  "Liberation Sans",
  "Noto Sans",
];

// Fonts that were removed (not available in render-service Docker image)
const REMOVED_FONTS = ["Montserrat", "Poppins"];

describe("PropertiesPanel Font List", () => {
  const mockTextLayer: SlideLayer = {
    id: "test-layer",
    type: "text",
    name: "Test Text",
    position: { x: 0, y: 0 },
    size: { width: 200, height: 50 },
    visible: true,
    locked: false,
    zIndex: 0,
    text: {
      baseContent: "Hello",
      translations: {},
      isTranslatable: true,
      style: {
        fontFamily: "Inter",
        fontSize: 24,
        fontWeight: "normal",
        fontStyle: "normal",
        color: "#FFFFFF",
        align: "left",
        lineHeight: 1.4,
      },
    },
  };

  it("should include all fonts available in render-service", () => {
    const mockUpdate = vi.fn();
    render(<PropertiesPanel layer={mockTextLayer} onUpdateLayer={mockUpdate} />);

    // Check each expected font is present as an option
    for (const font of EXPECTED_FONTS) {
      const option = screen.getByRole("option", { name: font });
      expect(option).toBeInTheDocument();
    }
  });

  it("should NOT include fonts not available in render-service", () => {
    const mockUpdate = vi.fn();
    render(<PropertiesPanel layer={mockTextLayer} onUpdateLayer={mockUpdate} />);

    // Verify removed fonts are NOT present
    for (const font of REMOVED_FONTS) {
      const option = screen.queryByRole("option", { name: font });
      expect(option).not.toBeInTheDocument();
    }
  });

  it("should render nothing when no layer selected", () => {
    const mockUpdate = vi.fn();
    render(<PropertiesPanel layer={undefined} onUpdateLayer={mockUpdate} />);

    expect(screen.getByText(/select a layer/i)).toBeInTheDocument();
  });

  it("should not show font selector for non-text layers", () => {
    const plateLayer: SlideLayer = {
      id: "plate-layer",
      type: "plate",
      name: "Test Plate",
      position: { x: 0, y: 0 },
      size: { width: 200, height: 100 },
      visible: true,
      locked: false,
      zIndex: 0,
      plate: {
        backgroundColor: "#FFFFFF",
        backgroundOpacity: 1,
        borderRadius: 8,
      },
    };

    const mockUpdate = vi.fn();
    render(<PropertiesPanel layer={plateLayer} onUpdateLayer={mockUpdate} />);

    // Should not have font select for plate layers
    const fontSelects = screen.queryAllByRole("combobox");
    const fontSelect = fontSelects.find((el) => 
      el.querySelector('option[value="Inter"]')
    );
    expect(fontSelect).toBeUndefined();
  });
});

describe("Font Synchronization Verification", () => {
  it("should document font requirements for render-service", () => {
    // This test documents the expected font configuration
    // If this test needs updating, render-service Dockerfile must also be updated
    
    const fontConfig = {
      // Fonts that MUST be installed in render-service Docker image
      required: EXPECTED_FONTS,
      
      // Fonts that MUST NOT be offered in UI (not installed in Docker)
      notAvailable: REMOVED_FONTS,
      
      // Default font for new text layers
      default: "Inter",
    };

    expect(fontConfig.required).toContain(fontConfig.default);
    expect(fontConfig.notAvailable).not.toContain(fontConfig.default);
  });
});

