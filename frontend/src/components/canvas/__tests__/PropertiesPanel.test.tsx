import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PropertiesPanel } from "../PropertiesPanel";
import type { SlideLayer } from "@/lib/api";

function makeTextLayer(overrides: Partial<SlideLayer>): SlideLayer {
  return {
    id: "l1",
    type: "text",
    name: "Title",
    position: { x: 101, y: 202 },
    size: { width: 303, height: 404 },
    visible: true,
    locked: false,
    zIndex: 0,
    opacity: 1,
    rotation: 0,
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
        verticalAlign: "top",
        lineHeight: 1.4,
      },
    },
    ...overrides,
  };
}

describe("PropertiesPanel", () => {
  it("shows placeholder when no layer selected", () => {
    render(<PropertiesPanel layer={undefined} onUpdateLayer={() => {}} />);
    expect(screen.getByText("Select a layer to edit its properties")).toBeInTheDocument();
  });

  it("updates name, position, and text content", () => {
    const layer = makeTextLayer({});
    const onUpdateLayer = vi.fn();

    render(<PropertiesPanel layer={layer} onUpdateLayer={onUpdateLayer} />);

    // Name
    const nameInput = screen.getByDisplayValue("Title");
    fireEvent.change(nameInput, { target: { value: "New Title" } });
    expect(onUpdateLayer).toHaveBeenCalledWith({ name: "New Title" });

    // X position (unique value 101)
    const xInput = screen.getByDisplayValue("101");
    fireEvent.change(xInput, { target: { value: "150" } });
    expect(onUpdateLayer).toHaveBeenCalledWith({ position: { x: 150, y: 202 } });

    // Text content
    const textarea = screen.getByDisplayValue("Hello");
    fireEvent.change(textarea, { target: { value: "Updated text" } });
    expect(onUpdateLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        text: expect.objectContaining({ baseContent: "Updated text" }),
      })
    );
  });
});


