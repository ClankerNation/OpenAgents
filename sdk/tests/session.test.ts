/**
 * SessionManager tests
 *
 * Tests cover:
 * - In-memory storage (no localStorage)
 * - Expiry detection and auto-refresh
 * - Refresh coalescing (mutex)
 * - Token rotation tracking
 * - Authentication flow
 * - Logout
 */
import { strict as assert } from "assert";

// Mock Wallet
class MockWallet {
  address = "0x1234567890abcdef1234567890abcdef12345678";
  async sendTransaction() {
    return "0xmocksignature";
  }
}

// Mock fetch for different scenarios
function createMockFetch(scenarios: Record<string, any>) {
  return async (url: string, _options?: RequestInit): Promise<any> => {
    const key = url.includes("/auth/login") ? "login" : "refresh";
    const scenario = scenarios[key];
    if (!scenario) {
      return {
        ok: false,
        status: 404,
        async json() {
          return { error: "not found" };
        },
      };
    }
    return {
      ok: scenario.ok ?? true,
      status: scenario.status ?? 200,
      async json() {
        return typeof scenario.response === "function"
          ? scenario.response()
          : scenario.response;
      },
    };
  };
}

export async function runTests(): Promise<{ passed: number; failed: number; errors: string[] }> {
  let passed = 0;
  let failed = 0;
  const errors: string[] = [];

  async function test(name: string, fn: () => Promise<void>) {
    try {
      await fn();
      passed++;
      console.log(`  ✓ ${name}`);
    } catch (err: any) {
      failed++;
      const msg = err?.message ?? String(err);
      errors.push(`${name}: ${msg}`);
      console.log(`  ✗ ${name}: ${msg}`);
    }
  }

  // Dynamically import the module
  const { SessionManager } = await import("../src/auth/session");

  console.log("\n📋 SessionManager Security Tests\n");

  await test("stores tokens in-memory only (no localStorage)", async () => {
    const wallet = new MockWallet();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = createMockFetch({
      login: {
        ok: true,
        response: {
          token: "test-token-abc",
          expiresAt: Math.floor(Date.now() / 1000) + 3600,
          refreshToken: "refresh-abc",
          walletAddress: wallet.address,
          tokenId: "tok-001",
        },
      },
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    await sm.authenticate();

    // Verify no localStorage was used
    assert.equal(
      typeof window !== "undefined" && (window as any).localStorage
        ? (window as any).localStorage.getItem(`session_${wallet.address}`)
        : null,
      null,
      "should not persist token to localStorage"
    );

    globalThis.fetch = originalFetch;
  });

  await test("getToken returns cached token if not expired", async () => {
    const wallet = new MockWallet();
    const token = {
      token: "test-token-abc",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "refresh-abc",
      walletAddress: wallet.address,
    };

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    // Manually set the token (simulating authenticate)
    (sm as any).currentToken = token;

    const result = await sm.getToken();
    assert.equal(result, "test-token-abc", "should return cached token");
  });

  await test("getToken auto-refreshes expired token", async () => {
    const wallet = new MockWallet();
    let refreshCalled = false;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = createMockFetch({
      refresh: {
        ok: true,
        response: () => {
          refreshCalled = true;
          return {
            token: "refreshed-token-xyz",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            refreshToken: "refresh-xyz",
            walletAddress: wallet.address,
            tokenId: "tok-002",
          };
        },
      },
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    // Set an expired token
    (sm as any).currentToken = {
      token: "old-token",
      expiresAt: Math.floor(Date.now() / 1000) - 60, // expired 1 min ago
      refreshToken: "old-refresh",
      walletAddress: wallet.address,
    };

    const result = await sm.getToken();
    assert.equal(refreshCalled, true, "refresh should be called");
    assert.equal(result, "refreshed-token-xyz", "should return refreshed token");

    globalThis.fetch = originalFetch;
  });

  await test("getToken authenticates if no token exists", async () => {
    const wallet = new MockWallet();
    let authCalled = false;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = createMockFetch({
      login: {
        ok: true,
        response: () => {
          authCalled = true;
          return {
            token: "fresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            refreshToken: "fresh-refresh",
            walletAddress: wallet.address,
          };
        },
      },
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    const result = await sm.getToken();
    assert.equal(authCalled, true, "authenticate should be called");
    assert.equal(result, "fresh-token", "should return fresh token");

    globalThis.fetch = originalFetch;
  });

  await test("refresh coalesces concurrent calls", async () => {
    const wallet = new MockWallet();
    let refreshCount = 0;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () => {
      return async (url: string) => {
        if (url.includes("/auth/refresh")) {
          refreshCount++;
          // Simulate a slow response
          await new Promise((r) => setTimeout(r, 50));
          return {
            ok: true,
            status: 200,
            async json() {
              return {
                token: `token-${refreshCount}`,
                expiresAt: Math.floor(Date.now() / 1000) + 3600,
                refreshToken: `refresh-${refreshCount}`,
                walletAddress: wallet.address,
                tokenId: `tok-${refreshCount}`,
              };
            },
          };
        }
        return { ok: false, status: 404, async json() { return {}; } };
      };
    })() as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    // Set an expired token so refresh is triggered
    (sm as any).currentToken = {
      token: "old-token",
      expiresAt: Math.floor(Date.now() / 1000) - 60,
      refreshToken: "old-refresh",
      walletAddress: wallet.address,
    };

    // Fire 3 concurrent refresh calls
    const [r1, r2, r3] = await Promise.all([
      sm.refresh(),
      sm.refresh(),
      sm.refresh(),
    ]);

    assert.equal(refreshCount, 1, "should only call refresh API once");
    assert.equal(r1.token, r2.token, "all callers should get same result");
    assert.equal(r2.token, r3.token, "all callers should get same result");

    globalThis.fetch = originalFetch;
  });

  await test("isTokenRevoked detects rotated tokens", async () => {
    const wallet = new MockWallet();

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    (sm as any).currentToken = {
      token: "old-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "old-refresh",
      walletAddress: wallet.address,
      tokenId: "tok-old",
    };

    const oldTokenId = (sm as any).currentToken.tokenId;
    (sm as any).rotatedTokenIds.add(oldTokenId);

    assert.equal(sm.isTokenRevoked("tok-old"), true, "old token should be revoked");
    assert.equal(sm.isTokenRevoked("tok-new"), false, "new token should not be revoked");
  });

  await test("logout clears in-memory token", async () => {
    const wallet = new MockWallet();

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    (sm as any).currentToken = {
      token: "test-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "test-refresh",
      walletAddress: wallet.address,
    };

    assert.equal(sm.isAuthenticated(), true, "should be authenticated before logout");
    sm.logout();
    assert.equal(sm.isAuthenticated(), false, "should not be authenticated after logout");
  });

  await test("isAuthenticated checks expiry", async () => {
    const wallet = new MockWallet();

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    // Set an expired token
    (sm as any).currentToken = {
      token: "expired-token",
      expiresAt: Math.floor(Date.now() / 1000) - 60,
      refreshToken: "expired-refresh",
      walletAddress: wallet.address,
    };

    assert.equal(
      sm.isAuthenticated(),
      false,
      "should return false for expired token even though currentToken is not null"
    );
  });

  await test("isAuthenticated returns true for valid token", async () => {
    const wallet = new MockWallet();

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    (sm as any).currentToken = {
      token: "valid-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "valid-refresh",
      walletAddress: wallet.address,
    };

    assert.equal(sm.isAuthenticated(), true, "should return true for valid token");
  });

  await test("authenticate returns session token", async () => {
    const wallet = new MockWallet();

    const originalFetch = globalThis.fetch;
    globalThis.fetch = createMockFetch({
      login: {
        ok: true,
        response: {
          token: "auth-token",
          expiresAt: Math.floor(Date.now() / 1000) + 3600,
          refreshToken: "auth-refresh",
          walletAddress: wallet.address,
          tokenId: "tok-auth",
        },
      },
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    const token = await sm.authenticate();

    assert.equal(token.token, "auth-token");
    assert.equal(token.refreshToken, "auth-refresh");
    assert.equal(token.walletAddress, wallet.address);

    globalThis.fetch = originalFetch;
  });

  await test("authenticate throws on failure", async () => {
    const wallet = new MockWallet();

    const originalFetch = globalThis.fetch;
    globalThis.fetch = createMockFetch({
      login: {
        ok: false,
        status: 401,
        response: { error: "unauthorized" },
      },
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    let threw = false;
    try {
      await sm.authenticate();
    } catch (err: any) {
      threw = true;
      assert.ok(err.message.includes("401"), "should include status code");
    }
    assert.equal(threw, true, "should have thrown on auth failure");

    globalThis.fetch = originalFetch;
  });

  await test("refresh handles refresh token failure gracefully", async () => {
    const wallet = new MockWallet();
    let loginAfterFailure = false;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string) => {
      if (url.includes("/auth/refresh")) {
        return {
          ok: false,
          status: 401,
          async json() {
            return { error: "refresh token expired" };
          },
        };
      }
      if (url.includes("/auth/login")) {
        loginAfterFailure = true;
        return {
          ok: true,
          status: 200,
          async json() {
            return {
              token: "post-failure-token",
              expiresAt: Math.floor(Date.now() / 1000) + 3600,
              refreshToken: "post-failure-refresh",
              walletAddress: wallet.address,
            };
          },
        };
      }
      return { ok: false, status: 404, async json() { return {}; } };
    }) as any;

    const sm = new SessionManager({
      wallet: wallet as any,
      apiBaseUrl: "https://api.test.com",
    });

    (sm as any).currentToken = {
      token: "expired-token",
      expiresAt: Math.floor(Date.now() / 1000) - 60,
      refreshToken: "stale-refresh",
      walletAddress: wallet.address,
    };

    const result = await sm.refresh();
    assert.equal(loginAfterFailure, true, "should fall back to authenticate on refresh failure");
    assert.equal(result.token, "post-failure-token");

    globalThis.fetch = originalFetch;
  });

  return { passed, failed, errors };
}

// Run tests if executed directly
runTests().then(({ passed, failed, errors }) => {
  console.log(`\n${passed} passed, ${failed} failed`);
  if (errors.length > 0) {
    process.exit(1);
  }
});
