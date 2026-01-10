import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({
  api: {
    getWorkspaceExports: vi.fn(),
    deleteWorkspaceExport: vi.fn(),
    getDownloadUrl: vi.fn(),
    getPptxDownloadUrl: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import WorkspacePage from "./page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("WorkspacePage downloads", () => {
  const openSpy = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).open = openSpy;
  });

  afterEach(() => {
    openSpy.mockReset();
  });

  it("uses API-provided filename for video downloads (no guessing)", async () => {
    (api.getWorkspaceExports as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exports: [
        {
          project_id: "proj",
          project_name: "My Project",
          version_id: "ver",
          lang: "en",
          video_file: "real-name-123.mp4",
          video_size_mb: 1.23,
          has_srt: true,
          has_pptx: false,
          pptx_file: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    (api.getDownloadUrl as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (_projectId: string, _versionId: string, _lang: string, filename: string) =>
        `http://api/download/${filename}`
    );

    renderWithQueryClient(<WorkspacePage />);

    await waitFor(() => {
      expect(screen.getByText("My Project")).toBeInTheDocument();
    });

    const videoBtn = screen.getByRole("button", { name: /video/i });
    fireEvent.click(videoBtn);

    expect(api.getDownloadUrl).toHaveBeenCalledWith("proj", "ver", "en", "real-name-123.mp4");
    expect(openSpy).toHaveBeenCalledWith("http://api/download/real-name-123.mp4", "_blank", "noreferrer,noopener");
  });

  it("derives SRT filename from the video filename when SRT exists", async () => {
    (api.getWorkspaceExports as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      exports: [
        {
          project_id: "proj",
          project_name: "My Project",
          version_id: "ver",
          lang: "en",
          video_file: "deck_en.mp4",
          video_size_mb: 1.23,
          has_srt: true,
          has_pptx: false,
          pptx_file: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    (api.getDownloadUrl as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (_projectId: string, _versionId: string, _lang: string, filename: string) =>
        `http://api/download/${filename}`
    );

    renderWithQueryClient(<WorkspacePage />);

    await waitFor(() => {
      expect(screen.getByText("My Project")).toBeInTheDocument();
    });

    const srtBtn = screen.getByRole("button", { name: /srt/i });
    fireEvent.click(srtBtn);

    expect(api.getDownloadUrl).toHaveBeenCalledWith("proj", "ver", "en", "deck_en.srt");
    expect(openSpy).toHaveBeenCalledWith("http://api/download/deck_en.srt", "_blank", "noreferrer,noopener");
  });
});


