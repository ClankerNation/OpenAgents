/**
 * Tests for SessionManager security fixes (bounty #25)
 *
 * Verifies:
 * 1. No localStorage — tokens stored in-memory only
 * 2. Expiry check — expired tokens auto-refresh
 * 3. Concurrent refresh coalescing
 * 4. Token rotation detection
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { SessionManager, type SessionToken } from "../src/auth/session";

// Mock Wallet
const mockWallet = {
  address: "0x1234567890abcdef",
  sendTransaction: vi.fn().mockResolvedValue("0xsig"),
};

const API_BASE = "https://api.test.com";

// Helper to create a session token
function makeToken(expiresInSeconds: number = 3600): SessionToken {
  return {
    token: `token_${Date.now()}`,
    expiresAt: Math.floor(Date.now() / 1000) + expiresInSeconds,
    refreshToken: `refresh_${Date.now()}`,
    walletAddress: mockWallet.address,
  };
}

describe("SessionManager — Security Fixes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("localStorage", undefined);
  });

  it("should store tokens in-memory only (no localStorage)", () => {
    // Ensure localStorage is not used
    const spySetItem = vi.fn();
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(),
      setItem: spySetItem,
      removeItem: vi.fn(),
    });

    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });

    // Access session internals via authenticate which stores the token
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(makeToken()),
    });

    sm.authenticate();
    // localStorage.setItem should NOT have been called
    expect(spySetItem).not.toHaveBeenCalled();
  });

  it("should return cached token when valid", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const token = makeToken(3600);

    // Inject session internally
    (sm as any).currentToken = token;

    const result = await sm.getToken();
    expect(result).toBe(token.token);
  });

  it("should auto-refresh expired token", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const expiredToken = makeToken(-60); // expired 60s ago
    const freshToken = makeToken(3600);

    (sm as any).currentToken = expiredToken;

    // Mock refresh endpoint
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(freshToken),
    });

    const result = await sm.getToken();
    expect(result).toBe(freshToken.token);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/auth/refresh"),
      expect.any(Object),
    );
  });

  it("should coalesce concurrent refresh calls", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const expiredToken = makeToken(-60);
    const freshToken = makeToken(3600);

    (sm as any).currentToken = expiredToken;

    let callCount = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      callCount++;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(freshToken),
      });
    });

    // Fire 3 concurrent getToken calls
    const results = await Promise.all([
      sm.getToken(),
      sm.getToken(),
      sm.getToken(),
    ]);

    // Should only have made 1 refresh API call
    expect(callCount).toBe(1);
    // All 3 should get the same token
    expect(results[0]).toBe(freshToken.token);
    expect(results[1]).toBe(freshToken.token);
    expect(results[2]).toBe(freshToken.token);
  });

  it("should detect token revocation after rotation", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const oldToken = makeToken(3600);
    const newToken = makeToken(3600);

    (sm as any).currentToken = oldToken;

    // Mock refresh — returns new token, which triggers rotation tracking
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(newToken),
    });

    await sm.refresh();

    // Old token should be marked as revoked
    expect(sm.isTokenRevoked(oldToken.token)).toBe(true);
    // New token should NOT be revoked
    expect(sm.isTokenRevoked(newToken.token)).toBe(false);
  });

  it("should return false for isAuthenticated with expired token", () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const expiredToken = makeToken(-60);

    (sm as any).currentToken = expiredToken;

    expect(sm.isAuthenticated()).toBe(false);
  });

  it("should return true for isAuthenticated with valid token", () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const validToken = makeToken(3600);

    (sm as any).currentToken = validToken;

    expect(sm.isAuthenticated()).toBe(true);
  });

  it("should clear in-memory state on logout", () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const token = makeToken(3600);

    (sm as any).currentToken = token;
    expect(sm.isAuthenticated()).toBe(true);

    sm.logout();
    expect(sm.isAuthenticated()).toBe(false);
    expect((sm as any).currentToken).toBeNull();
  });

  it("should authenticate successfully", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const token = makeToken(3600);

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(token),
    });

    const result = await sm.authenticate();
    expect(result.token).toBe(token.token);
    expect(sm.isAuthenticated()).toBe(true);
  });

  it("should fail gracefully on failed refresh", async () => {
    const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: API_BASE });
    const expiredToken = makeToken(-60);
    const newToken = makeToken(3600);

    (sm as any).currentToken = expiredToken;

    // First refresh fails
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 401 })
      // Falls back to authenticate
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(newToken),
      });

    const result = await sm.getToken();
    expect(result).toBe(newToken.token);
  });
});
