import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", () => {
  return {
    api: {
      getProjectAssets: vi.fn(),
      uploadAsset: vi.fn(),
      deleteAsset: vi.fn(),
      getAssetUrl: (url: string) => url,
    },
  };
});

import { api } from "@/lib/api";
import { AssetLibrary } from "../AssetLibrary";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe("AssetLibrary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state and closes", async () => {
    const user = userEvent.setup();
    (api.getProjectAssets as any).mockResolvedValue({ assets: [], total: 0 });

    const onSelect = vi.fn();
    const onClose = vi.fn();

    render(
      <QueryClientProvider client={makeQueryClient()}>
        <AssetLibrary projectId="p1" onSelect={onSelect} onClose={onClose} />
      </QueryClientProvider>
    );

    expect(await screen.findByText("No assets yet")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});


