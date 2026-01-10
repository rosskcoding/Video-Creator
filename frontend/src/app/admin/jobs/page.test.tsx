import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Keep tests hermetic
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({
  api: {
    getAllJobs: vi.fn(),
    cancelJob: vi.fn(),
    cancelAllProjectJobs: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import AdminJobsPage from "./page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("AdminJobsPage", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn> | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy?.mockRestore();
    consoleErrorSpy = null;
  });

  it("does not emit React key warning when rendering jobs list", async () => {
    (api.getAllJobs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "job-12345678-aaaa-bbbb-cccc-ddddeeeeffff",
        lang: "en",
        job_type: "render",
        status: "done",
        progress_pct: 100,
        download_video_url: "/api/render/projects/proj/versions/ver/download/en/deck_en.mp4",
        download_srt_url: null,
        error_message: null,
        started_at: null,
        finished_at: null,
        project_id: "proj",
        project_name: "Test Project",
        version_id: "ver",
      },
    ]);

    renderWithQueryClient(<AdminJobsPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Project")).toBeInTheDocument();
    });

    // React key warning would be logged to console.error
    const keyWarnings = (consoleErrorSpy?.mock.calls || []).filter((call: unknown[]) =>
      call
        .map(String)
        .join(" ")
        .includes('Each child in a list should have a unique "key" prop')
    );
    expect(keyWarnings).toHaveLength(0);
  });

  it("adds rel=noreferrer noopener to target=_blank download links", async () => {
    (api.getAllJobs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "job-abcdef12-aaaa-bbbb-cccc-ddddeeeeffff",
        lang: "en",
        job_type: "render",
        status: "done",
        progress_pct: 100,
        download_video_url: "/api/render/projects/proj/versions/ver/download/en/deck_en.mp4",
        download_srt_url: null,
        error_message: null,
        started_at: null,
        finished_at: null,
        project_id: "proj",
        project_name: "Test Project",
        version_id: "ver",
      },
    ]);

    renderWithQueryClient(<AdminJobsPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Project")).toBeInTheDocument();
    });

    // Expand the row
    const projectCell = screen.getByText("Test Project");
    const row = projectCell.closest("tr");
    expect(row).toBeTruthy();
    fireEvent.click(row!);

    await waitFor(() => {
      expect(screen.getByText("Download Video")).toBeInTheDocument();
    });

    const link = screen.getByText("Download Video").closest("a");
    expect(link).toBeTruthy();
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });
});


