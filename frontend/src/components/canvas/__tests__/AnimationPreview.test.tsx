import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { AnimationPreview, getLayerAnimationStyle } from "../AnimationPreview";
import type { SlideLayer } from "@/lib/api";

function makeLayer(overrides: Partial<SlideLayer>): SlideLayer {
  return {
    id: "layer-1",
    type: "text",
    name: "Test Layer",
    position: { x: 0, y: 0 },
    size: { width: 100, height: 50 },
    visible: true,
    locked: false,
    zIndex: 0,
    ...overrides,
  };
}

describe("AnimationPreview", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders with no layers", () => {
    render(<AnimationPreview layers={[]} duration={10} />);
    expect(screen.getByText("No layers to animate")).toBeInTheDocument();
  });

  it("renders layers with animations", () => {
    const layers: SlideLayer[] = [
      makeLayer({
        id: "l1",
        name: "Fade Layer",
        animation: {
          entrance: {
            type: "fadeIn",
            duration: 0.3,
            delay: 0,
            easing: "easeOut",
            trigger: { type: "start" },
          },
        },
      }),
      makeLayer({
        id: "l2",
        name: "Slide Layer",
        animation: {
          entrance: {
            type: "slideLeft",
            duration: 0.5,
            delay: 0.2,
            easing: "easeInOut",
            trigger: { type: "time", seconds: 1 },
          },
          exit: {
            type: "fadeOut",
            duration: 0.3,
            delay: 0,
            easing: "easeOut",
            trigger: { type: "end" },
          },
        },
      }),
    ];

    render(<AnimationPreview layers={layers} duration={10} />);

    expect(screen.getByText("Fade Layer")).toBeInTheDocument();
    expect(screen.getByText("Slide Layer")).toBeInTheDocument();
    expect(screen.getByText("fadeIn")).toBeInTheDocument();
    expect(screen.getByText("slideLeft")).toBeInTheDocument();
    expect(screen.getByText("fadeOut")).toBeInTheDocument();
  });

  it("has play/pause controls", () => {
    const layers: SlideLayer[] = [makeLayer({ id: "l1", name: "Layer 1" })];
    render(<AnimationPreview layers={layers} duration={10} />);

    // Should have multiple buttons for controls
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(2); // Play and Reset buttons
  });

  it("displays time format correctly", () => {
    render(<AnimationPreview layers={[makeLayer({})]} duration={65} />);
    expect(screen.getByText(/0:00.0/)).toBeInTheDocument();
    expect(screen.getByText(/1:05.0/)).toBeInTheDocument();
  });
});

describe("getLayerAnimationStyle", () => {
  it("returns full opacity when no animation", () => {
    const layer = makeLayer({});
    const style = getLayerAnimationStyle(layer, 0);
    expect(style.opacity).toBe(1);
  });

  it("returns hidden before entrance animation starts", () => {
    const layer = makeLayer({
      animation: {
        entrance: {
          type: "fadeIn",
          duration: 0.5,
          delay: 1,
          easing: "easeOut",
          trigger: { type: "start" },
        },
      },
    });
    const style = getLayerAnimationStyle(layer, 0);
    expect(style.opacity).toBe(0);
    expect(style.visibility).toBe("hidden");
  });

  it("animates opacity during fadeIn", () => {
    const layer = makeLayer({
      animation: {
        entrance: {
          type: "fadeIn",
          duration: 1,
          delay: 0,
          easing: "linear",
          trigger: { type: "start" },
        },
      },
    });
    
    // At t=0.5, should be 50% through animation with linear easing
    const style = getLayerAnimationStyle(layer, 0.5);
    expect(style.opacity).toBeCloseTo(0.5, 1);
  });

  it("returns transform for slide animations", () => {
    const layer = makeLayer({
      animation: {
        entrance: {
          type: "slideLeft",
          duration: 1,
          delay: 0,
          easing: "linear",
          trigger: { type: "start" },
        },
      },
    });
    
    const style = getLayerAnimationStyle(layer, 0.5);
    expect(style.transform).toBeDefined();
    expect(style.transform).toContain("translateX");
  });

  it("handles time-based triggers", () => {
    const layer = makeLayer({
      animation: {
        entrance: {
          type: "fadeIn",
          duration: 0.5,
          delay: 0,
          easing: "linear",
          trigger: { type: "time", seconds: 2 },
        },
      },
    });
    
    // Before trigger time, should be hidden
    const styleBefore = getLayerAnimationStyle(layer, 1);
    expect(styleBefore.opacity).toBe(0);
    
    // After trigger time, should be animating
    const styleAfter = getLayerAnimationStyle(layer, 2.25);
    expect(styleAfter.opacity).toBeCloseTo(0.5, 1);
  });

  it("handles exit animations at slide end", () => {
    const layer = makeLayer({
      animation: {
        exit: {
          type: "fadeOut",
          duration: 0.5,
          delay: 0,
          easing: "linear",
          trigger: { type: "end", offsetSeconds: -0.5 },
        },
      },
    });
    
    // At slide duration 10, with offset -0.5, trigger at 9.5
    // At t=9.75, should be 50% through fade out
    const style = getLayerAnimationStyle(layer, 9.75, 10);
    expect(style.opacity).toBeCloseTo(0.5, 1);
  });
});

