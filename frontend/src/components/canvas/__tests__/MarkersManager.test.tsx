import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { MarkersManager } from "../MarkersManager";

// Mock the api module
vi.mock("@/lib/api", () => ({
  api: {
    getSlideMarkers: vi.fn().mockResolvedValue({
      markers: [],
      slide_id: "slide-1",
      lang: "en",
    }),
    updateSlideMarkers: vi.fn().mockResolvedValue({
      markers: [],
      slide_id: "slide-1",
      lang: "en",
    }),
  },
}));

// Import after mock
import { api } from "@/lib/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const createWrapper = () => TestWrapper;

describe("MarkersManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with script text", async () => {
    const scriptText = "Hello world this is a test";

    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText={scriptText}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText("Markers (0)")).toBeInTheDocument();
    
    // Wait for the words to render
    await waitFor(() => {
      expect(screen.getByText("Hello")).toBeInTheDocument();
      expect(screen.getByText("world")).toBeInTheDocument();
      expect(screen.getByText("test")).toBeInTheDocument();
    });
  });

  it("shows empty state when no script text", () => {
    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText=""
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText("No script text")).toBeInTheDocument();
  });

  it("shows add marker form when clicking Add button", async () => {
    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText="Hello world"
      />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Marker name...")).toBeInTheDocument();
      expect(screen.getByText("Click a word below to set marker position")).toBeInTheDocument();
    });
  });

  it("calls onSelectWord when word is clicked (not in add mode)", async () => {
    const onSelectWord = vi.fn();

    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText="Hello world"
        onSelectWord={onSelectWord}
      />,
      { wrapper: createWrapper() }
    );

    // Wait for words to render
    await waitFor(() => {
      expect(screen.getByText("Hello")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Hello"));

    expect(onSelectWord).toHaveBeenCalledWith("Hello", 0, 5);
  });

  it("selects word when in add marker mode", async () => {
    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText="Hello world"
      />,
      { wrapper: createWrapper() }
    );

    // Enter add marker mode
    fireEvent.click(screen.getByText("Add"));

    // Wait for words to render
    await waitFor(() => {
      expect(screen.getByText("Hello")).toBeInTheDocument();
    });

    // Click on a word
    fireEvent.click(screen.getByText("Hello"));

    // Should show the selected word
    await waitFor(() => {
      expect(screen.getByText('Selected: "Hello"')).toBeInTheDocument();
    });
  });

  it("renders existing markers from API", async () => {
    (api.getSlideMarkers as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      markers: [
        {
          id: "marker-1",
          name: "Important",
          charStart: 0,
          charEnd: 5,
          wordText: "Hello",
        },
      ],
      slide_id: "slide-1",
      lang: "en",
    });

    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText="Hello world"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByText("Markers (1)")).toBeInTheDocument();
      expect(screen.getByText("Important")).toBeInTheDocument();
      expect(screen.getByText('"Hello"')).toBeInTheDocument();
    });
  });

  it("highlights words that have markers", async () => {
    (api.getSlideMarkers as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      markers: [
        {
          id: "marker-1",
          name: "Important",
          charStart: 0,
          charEnd: 5,
          wordText: "Hello",
        },
      ],
      slide_id: "slide-1",
      lang: "en",
    });

    render(
      <MarkersManager
        slideId="slide-1"
        lang="en"
        scriptText="Hello world"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      const helloWord = screen.getByText("Hello");
      // Should have marker styling (yellow background)
      expect(helloWord.className).toContain("bg-yellow");
    });
  });
});

