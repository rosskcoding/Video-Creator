import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { LayerPanel } from "../LayerPanel";
import type { SlideLayer } from "@/lib/api";

function makeLayer(overrides: Partial<SlideLayer>): SlideLayer {
  return {
    id: "layer-1",
    type: "text",
    name: "Layer",
    position: { x: 0, y: 0 },
    size: { width: 100, height: 50 },
    visible: true,
    locked: false,
    zIndex: 0,
    ...overrides,
  };
}

describe("LayerPanel", () => {
  const nowSpy = vi.spyOn(Date, "now");
  const randomSpy = vi.spyOn(Math, "random");

  beforeEach(() => {
    nowSpy.mockReturnValue(1234567890);
    randomSpy.mockReturnValue(0.123456);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders layers and calls onSelectLayer", () => {
    const layers: SlideLayer[] = [
      makeLayer({ id: "l1", name: "Text 1", type: "text", zIndex: 0 }),
      makeLayer({ id: "l2", name: "Plate 1", type: "plate", zIndex: 1 }),
    ];

    const onSelectLayer = vi.fn();
    const onUpdateLayer = vi.fn();
    const onDeleteLayer = vi.fn();
    const onReorderLayers = vi.fn();

    render(
      <LayerPanel
        layers={layers}
        selectedLayerId={null}
        onSelectLayer={onSelectLayer}
        onUpdateLayer={onUpdateLayer}
        onDeleteLayer={onDeleteLayer}
        onReorderLayers={onReorderLayers}
      />
    );

    expect(screen.getByText("Layers")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Plate 1"));
    expect(onSelectLayer).toHaveBeenCalledWith("l2");
  });

  it("reorders layers via Move up", () => {
    const layers: SlideLayer[] = [
      makeLayer({ id: "l1", name: "Text 1", type: "text", zIndex: 0 }),
      makeLayer({ id: "l2", name: "Plate 1", type: "plate", zIndex: 1 }),
    ];

    const onSelectLayer = vi.fn();
    const onUpdateLayer = vi.fn();
    const onDeleteLayer = vi.fn();
    const onReorderLayers = vi.fn();

    render(
      <LayerPanel
        layers={layers}
        selectedLayerId={"l1"}
        onSelectLayer={onSelectLayer}
        onUpdateLayer={onUpdateLayer}
        onDeleteLayer={onDeleteLayer}
        onReorderLayers={onReorderLayers}
      />
    );

    fireEvent.click(screen.getByTitle("Move up"));
    expect(onReorderLayers).toHaveBeenCalledTimes(1);
    const reordered = onReorderLayers.mock.calls[0]?.[0] as SlideLayer[];
    expect(reordered.map((l) => l.id)).toEqual(["l2", "l1"]);
  });

  it("duplicates and deletes the selected layer", () => {
    const layers: SlideLayer[] = [
      makeLayer({ id: "l1", name: "Text 1", type: "text", zIndex: 0, position: { x: 10, y: 20 } }),
      makeLayer({ id: "l2", name: "Plate 1", type: "plate", zIndex: 1, position: { x: 30, y: 40 } }),
    ];

    const onSelectLayer = vi.fn();
    const onUpdateLayer = vi.fn();
    const onDeleteLayer = vi.fn();
    const onReorderLayers = vi.fn();

    render(
      <LayerPanel
        layers={layers}
        selectedLayerId={"l2"}
        onSelectLayer={onSelectLayer}
        onUpdateLayer={onUpdateLayer}
        onDeleteLayer={onDeleteLayer}
        onReorderLayers={onReorderLayers}
      />
    );

    fireEvent.click(screen.getByTitle("Duplicate"));
    expect(onReorderLayers).toHaveBeenCalledTimes(1);

    const newLayers = onReorderLayers.mock.calls[0]?.[0] as SlideLayer[];
    expect(newLayers).toHaveLength(3);

    const duplicated = newLayers[2];
    expect(duplicated.name).toContain("(copy)");
    expect(duplicated.position).toEqual({ x: 50, y: 60 });
    expect(duplicated.zIndex).toBe(2);

    fireEvent.click(screen.getByTitle("Delete"));
    expect(onDeleteLayer).toHaveBeenCalledWith("l2");
  });
});


