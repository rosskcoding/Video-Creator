import { describe, it, expect, vi, beforeEach } from "vitest";

// Capture the response error interceptor installed by api.ts
let responseErrorInterceptor: ((error: any) => Promise<any>) | undefined;

const clientMock = {
  interceptors: {
    request: { use: vi.fn() },
    response: {
      use: vi.fn((_onFulfilled: any, onRejected: any) => {
        responseErrorInterceptor = onRejected;
      }),
    },
  },
};

// axios is both callable (axios(config)) and has helpers (axios.create, axios.get)
const axiosFn = vi.fn();
(axiosFn as any).create = vi.fn(() => clientMock);
(axiosFn as any).get = vi.fn();

vi.mock("axios", () => ({
  default: axiosFn,
}));

describe("api.ts CSRF retry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    responseErrorInterceptor = undefined;
  });

  it("refreshes CSRF token and retries the original request once", async () => {
    process.env.NEXT_PUBLIC_API_URL = "http://api.example";

    // Ensure a fresh import so API_URL picks up the env var
    vi.resetModules();
    await import("../api");

    expect(responseErrorInterceptor).toBeTypeOf("function");

    (axiosFn as any).get.mockResolvedValue({ data: { csrf_token: "csrf-123" } });
    (axiosFn as any).mockResolvedValue({ data: { ok: true } });

    const originalRequest: any = { headers: {} };
    const error: any = {
      response: { status: 403, data: { detail: "CSRF token missing or invalid" } },
      config: originalRequest,
    };

    const result = await responseErrorInterceptor!(error);

    expect((axiosFn as any).get).toHaveBeenCalledWith("http://api.example/api/auth/csrf-token", {
      withCredentials: true,
    });
    expect(originalRequest._csrfRetry).toBe(true);
    expect(originalRequest.headers["X-CSRF-Token"]).toBe("csrf-123");
    expect(axiosFn).toHaveBeenCalledWith(originalRequest);
    expect(result).toEqual({ data: { ok: true } });
  });
});


