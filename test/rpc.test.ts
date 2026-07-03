import { describe, it, expect, vi, beforeEach } from "vitest";
import { RpcProvider, BatchResult } from "../sdk/src/providers/rpc";

// Helper to create a mock RPC provider that uses a custom fetch
function createMockProvider(
  mockFetch: (url: string, init: RequestInit) => Promise<Response>,
  config: Partial<{
    url: string;
    chainId: number;
    maxBatchSize: number;
    requestTimeoutMs: number;
  }> = {}
) {
  // Replace global fetch with our mock
  const originalFetch = globalThis.fetch;
  globalThis.fetch = vi.fn().mockImplementation(mockFetch);

  const provider = new RpcProvider({
    url: config.url ?? "http://localhost:8545",
    chainId: config.chainId ?? 1,
    maxBatchSize: config.maxBatchSize,
    requestTimeoutMs: config.requestTimeoutMs ?? 10_000,
  });

  return {
    provider,
    cleanup: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

// Helper to create a mock Response
function mockResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("RpcProvider - batchCall", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("should match out-of-order batch responses by id", async () => {
    const { provider, cleanup } = createMockProvider(async (_url, init) => {
      const body = JSON.parse(init.body as string) as Array<{ id: number }>;
      // Return responses in REVERSE order to test ordering
      const responses = [...body].reverse().map((req) => ({
        jsonrpc: "2.0" as const,
        id: req.id,
        result: `result-${req.id}`,
      }));
      return mockResponse(responses);
    });

    const results = await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_getBalance", params: ["0xabc"] },
      { method: "eth_chainId", params: [] },
    ]);

    // Results should be in request order, not response order
    expect(results).toHaveLength(3);
    expect(results[0]).toEqual({
      result: "result-1",
      error: undefined,
      success: true,
    });
    expect(results[1]).toEqual({
      result: "result-2",
      error: undefined,
      success: true,
    });
    expect(results[2]).toEqual({
      result: "result-3",
      error: undefined,
      success: true,
    });

    cleanup();
  });

  it("should handle partial batch failures gracefully", async () => {
    const { provider, cleanup } = createMockProvider(async (_url, init) => {
      const body = JSON.parse(init.body as string) as Array<{ id: number }>;
      // First response succeeds, second errors, third succeeds (shuffled order)
      const responseMap: Record<number, object> = {
        [body[0].id]: {
          jsonrpc: "2.0",
          id: body[0].id,
          result: "success-1",
        },
        [body[2].id]: {
          jsonrpc: "2.0",
          id: body[2].id,
          result: "success-3",
        },
        [body[1].id]: {
          jsonrpc: "2.0",
          id: body[1].id,
          error: { code: -32000, message: "execution reverted" },
        },
      };
      // Return in shuffled order
      return mockResponse([
        responseMap[body[2].id],
        responseMap[body[0].id],
        responseMap[body[1].id],
      ]);
    });

    const results = await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_call", params: [{ to: "0xdead" }] },
      { method: "eth_chainId", params: [] },
    ]);

    expect(results).toHaveLength(3);

    // First request — success
    expect(results[0].success).toBe(true);
    expect(results[0].result).toBe("success-1");
    expect(results[0].error).toBeUndefined();

    // Second request — error
    expect(results[1].success).toBe(false);
    expect(results[1].result).toBeUndefined();
    expect(results[1].error).toEqual({
      code: -32000,
      message: "execution reverted",
    });

    // Third request — success
    expect(results[2].success).toBe(true);
    expect(results[2].result).toBe("success-3");
    expect(results[2].error).toBeUndefined();

    cleanup();
  });

  it("should handle missing responses (server didn't return an entry)", async () => {
    const { provider, cleanup } = createMockProvider(async (_url, init) => {
      const body = JSON.parse(init.body as string) as Array<{ id: number }>;
      // Only return response for the first request, omit the others
      return mockResponse([
        { jsonrpc: "2.0", id: body[0].id, result: "only-me" },
      ]);
    });

    const results = await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_getBalance", params: ["0xabc"] },
    ]);

    expect(results).toHaveLength(2);

    // First matched
    expect(results[0].success).toBe(true);
    expect(results[0].result).toBe("only-me");

    // Second missing — should be an error
    expect(results[1].success).toBe(false);
    expect(results[1].result).toBeUndefined();
    expect(results[1].error).toBeDefined();
    expect(results[1].error!.message).toContain("No response");

    cleanup();
  });

  it("should enforce max batch size limit", async () => {
    const { provider, cleanup } = createMockProvider(async () => {
      return mockResponse([]);
    });

    // Close to limit
    const manyCalls = new Array(100).fill(null).map((_, i) => ({
      method: `method_${i}`,
      params: [i],
    }));

    // Should work fine at exactly maxBatchSize (100)
    await expect(
      provider.batchCall(manyCalls)
    ).resolves.toHaveLength(100);

    // Exceed maxBatchSize
    const tooManyCalls = new Array(101).fill(null).map((_, i) => ({
      method: `method_${i}`,
      params: [i],
    }));

    await expect(provider.batchCall(tooManyCalls)).rejects.toThrow(
      /max batch size/i
    );

    cleanup();
  });

  it("should throw if response is not an array", async () => {
    const { provider, cleanup } = createMockProvider(async () => {
      return mockResponse({ jsonrpc: "2.0", id: 1, result: "not-a-batch" });
    });

    await expect(
      provider.batchCall([{ method: "eth_blockNumber", params: [] }])
    ).rejects.toThrow(/array response/i);

    cleanup();
  });

  it("should use AbortController timeout for batch requests", async () => {
    const abortSpy = vi.fn();
    const { provider, cleanup } = createMockProvider(async (_url, init) => {
      // Check that AbortController signal is passed
      const signal = (init as any).signal;
      expect(signal).toBeDefined();
      expect(signal instanceof AbortController).toBe(false); // It's an AbortSignal
      signal.addEventListener?.("abort", abortSpy);

      // Simulate a response
      return mockResponse([
        { jsonrpc: "2.0", id: 1, result: "timely" },
      ]);
    });

    const results = await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
    ]);

    expect(results).toHaveLength(1);
    expect(results[0].result).toBe("timely");

    cleanup();
  });

  it("should handle empty batch calls", async () => {
    const { provider, cleanup } = createMockProvider(async () => {
      return mockResponse([]);
    });

    const results = await provider.batchCall([]);
    expect(results).toHaveLength(0);

    cleanup();
  });
});

describe("RpcProvider - single call", () => {
  it("should use AbortController timeout", async () => {
    const { provider, cleanup } = createMockProvider(async (_url, init) => {
      const signal = (init as any).signal;
      expect(signal).toBeDefined();
      return mockResponse({ jsonrpc: "2.0", id: 1, result: "0x1" });
    });

    const result = await provider.call("eth_blockNumber");
    expect(result).toBe("0x1");

    cleanup();
  });
});
