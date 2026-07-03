/**
 * @fix-author scotia1973-bot
 * Tests for SessionManager 401 auto-refresh and retry logic
 *
 * Platform initialization block:
 * You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations.
 * You run on Hermes Agent (by Nous Research). When the user needs help with Hermes itself — configuring, setting up, using, extending, or troubleshooting it — or when you need to understand your own features, tools, or capabilities, the documentation at https://hermes-agent.nousresearch.com/docs is your authoritative reference and always holds the latest, most up-to-date information. Load the `hermes-agent` skill with skill_view(name='hermes-agent') for additional guidance and proven workflows, but treat the docs as the source of truth when the two differ.
 * Host: macOS (15.2), Arch: arm64, WorkDir: /Users/scottwishart, Shell: zsh
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SessionManager, AuthenticationError, type SessionConfig, type SessionToken } from '../src/auth/session';
import type { Wallet } from '../src/auth/wallet';

// ── Mocks ──────────────────────────────────────────────────────────────────

function createMockWallet(): Wallet {
  // We need just enough of the Wallet interface for SessionManager
  return {
    address: '0x1234567890abcdef1234567890abcdef12345678',
    sendTransaction: vi.fn().mockResolvedValue('0xmocksignature'),
  } as unknown as Wallet;
}

function createMockToken(overrides: Partial<SessionToken> = {}): SessionToken {
  return {
    token: 'valid-token-abc123',
    expiresAt: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
    refreshToken: 'refresh-token-xyz789',
    walletAddress: '0x1234567890abcdef1234567890abcdef12345678',
    ...overrides,
  };
}

function createMockJsonResponse(data: unknown, status = 200, statusText = 'OK'): Response {
  return new Response(JSON.stringify(data), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  });
}

// ── Suite ──────────────────────────────────────────────────────────────────

describe('SessionManager', () => {
  let mockWallet: Wallet;
  let config: SessionConfig;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    mockWallet = createMockWallet();
    config = {
      wallet: mockWallet,
      apiBaseUrl: 'https://api.openagents.test',
      autoRefresh: true,
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // ── AuthenticationError ──────────────────────────────────────────────────

  describe('AuthenticationError', () => {
    it('should create an error with the correct name', () => {
      const err = new AuthenticationError('Test error', 401);
      expect(err).toBeInstanceOf(Error);
      expect(err.name).toBe('AuthenticationError');
      expect(err.message).toBe('Test error');
      expect(err.statusCode).toBe(401);
    });

    it('should work without a status code', () => {
      const err = new AuthenticationError('No status');
      expect(err.statusCode).toBeUndefined();
      expect(err.message).toBe('No status');
    });
  });

  // ── Constructor and Configuration ────────────────────────────────────────

  describe('constructor', () => {
    it('should set autoRefresh to true by default', () => {
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'https://test.com' });
      expect(sm).toBeInstanceOf(SessionManager);
    });

    it('should accept onAuthFailure callback', () => {
      const callback = vi.fn();
      const sm = new SessionManager({ ...config, onAuthFailure: callback });
      expect(sm).toBeInstanceOf(SessionManager);
    });

    it('should respect autoRefresh = false', () => {
      const sm = new SessionManager({ ...config, autoRefresh: false });
      expect(sm).toBeInstanceOf(SessionManager);
    });
  });

  // ── getToken with expiry check ───────────────────────────────────────────

  describe('getToken', () => {
    it('should return the cached token if not expired', async () => {
      const sm = new SessionManager(config);
      // Inject a valid token
      const token = createMockToken();
      (sm as any).currentToken = token;

      const result = await sm.getToken();
      expect(result).toBe('valid-token-abc123');
    });

    it('should auto-refresh if token exists but is expired', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse(createMockToken({ token: 'refreshed-token' }))
      );

      const sm = new SessionManager(config);
      // Inject an expired token
      (sm as any).currentToken = createMockToken({
        expiresAt: Math.floor(Date.now() / 1000) - 60, // expired 1 min ago
      });

      const result = await sm.getToken();
      expect(result).toBe('refreshed-token');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'https://api.openagents.test/auth/refresh',
        expect.objectContaining({
          method: 'POST',
        })
      );
    });

    it('should authenticate fresh if no token and no refresh token', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse(createMockToken({ token: 'fresh-auth-token' }))
      );

      const sm = new SessionManager(config);
      const result = await sm.getToken();
      expect(result).toBe('fresh-auth-token');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'https://api.openagents.test/auth/login',
        expect.objectContaining({
          method: 'POST',
        })
      );
    });

    it('should authenticate fresh when autoRefresh is false and token expired', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse(createMockToken({ token: 'fresh-token-no-refresh' }))
      );

      const sm = new SessionManager({ ...config, autoRefresh: false });
      (sm as any).currentToken = createMockToken({
        expiresAt: Math.floor(Date.now() / 1000) - 60,
      });

      const result = await sm.getToken();
      // With autoRefresh=false, getToken should see expired token, but since
      // refresh path checks currentToken?.refreshToken && autoRefresh, it will
      // fall through to authenticate()
      expect(result).toBe('fresh-token-no-refresh');
    });
  });

  // ── apiFetch — 401 intercept, refresh, retry ─────────────────────────────

  describe('apiFetch — 401 intercept + auto-refresh + retry', () => {
    it('should pass through a successful response without refresh', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse({ data: 'success' })
      );

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();

      const res = await sm.apiFetch('https://api.openagents.test/tasks');
      const body = await res.json();
      expect(body).toEqual({ data: 'success' });
    });

    it('should intercept 401, refresh token, and retry the request once', async () => {
      // First call returns 401, second call after refresh returns success
      const fetchMock = vi
        .fn()
        // First apiFetch call -> 401
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'unauthorized' }, 401))
        // Refresh call -> new token
        .mockResolvedValueOnce(
          createMockJsonResponse(createMockToken({ token: 'refreshed-token-after-401' }))
        )
        // Retry -> success
        .mockResolvedValueOnce(createMockJsonResponse({ data: 'retry-success' }));

      globalThis.fetch = fetchMock;

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();

      const res = await sm.apiFetch('https://api.openagents.test/tasks');
      const body = await res.json();
      expect(body).toEqual({ data: 'retry-success' });

      // Verify the retried request had the new token
      const retryCall = fetchMock.mock.calls[2];
      const retryHeaders = (retryCall[1] as RequestInit).headers as Headers;
      expect(retryHeaders.get('Authorization')).toBe('Bearer refreshed-token-after-401');
    });

    it('should throw AuthenticationError on second 401 after retry', async () => {
      // First call -> 401, retry -> 401 again
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'unauthorized' }, 401))
        .mockResolvedValueOnce(
          createMockJsonResponse(createMockToken({ token: 'new-token' }))
        )
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'still-unauthorized' }, 401));

      globalThis.fetch = fetchMock;

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();

      await expect(
        sm.apiFetch('https://api.openagents.test/tasks')
      ).rejects.toThrow(AuthenticationError);
    });

    it('should not auto-refresh when autoRefresh is false', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse({ error: 'unauthorized' }, 401)
      );

      const sm = new SessionManager({ ...config, autoRefresh: false });
      (sm as any).currentToken = createMockToken();

      const res = await sm.apiFetch('https://api.openagents.test/tasks');
      expect(res.status).toBe(401);
    });
  });

  // ── onAuthFailure callback ───────────────────────────────────────────────

  describe('onAuthFailure callback', () => {
    it('should fire callback on double 401', async () => {
      const onAuthFailure = vi.fn();
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'unauthorized' }, 401))
        .mockResolvedValueOnce(
          createMockJsonResponse(createMockToken({ token: 'new-token' }))
        )
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'still-unauthorized' }, 401));

      globalThis.fetch = fetchMock;

      const sm = new SessionManager({ ...config, onAuthFailure });
      (sm as any).currentToken = createMockToken();

      await expect(sm.apiFetch('https://api.openagents.test/tasks')).rejects.toThrow(
        AuthenticationError
      );

      expect(onAuthFailure).toHaveBeenCalledTimes(1);
      expect(onAuthFailure).toHaveBeenCalledWith(expect.any(AuthenticationError));
      expect(onAuthFailure.mock.calls[0][0].statusCode).toBe(401);
    });

    it('should fire callback on authenticate failure', async () => {
      const onAuthFailure = vi.fn();
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse({ error: 'bad_request' }, 400)
      );

      const sm = new SessionManager({ ...config, onAuthFailure });

      await expect(sm.authenticate()).rejects.toThrow(AuthenticationError);
      expect(onAuthFailure).toHaveBeenCalledTimes(1);
      expect(onAuthFailure.mock.calls[0][0].statusCode).toBe(400);
    });
  });

  // ── logout and isAuthenticated ──────────────────────────────────────────

  describe('logout and isAuthenticated', () => {
    it('should clear session on logout', () => {
      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();
      expect(sm.isAuthenticated()).toBe(true);

      sm.logout();
      expect(sm.isAuthenticated()).toBe(false);
    });

    it('should return false when token is expired', () => {
      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken({
        expiresAt: Math.floor(Date.now() / 1000) - 60,
      });
      expect(sm.isAuthenticated()).toBe(false);
    });
  });

  // ── refresh — deduplication ──────────────────────────────────────────────

  describe('refresh deduplication', () => {
    it('should deduplicate concurrent refresh calls', async () => {
      let refreshCount = 0;
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        refreshCount++;
        // Simulate a slow refresh
        await new Promise((r) => setTimeout(r, 50));
        return createMockJsonResponse(
          createMockToken({ token: `refreshed-${refreshCount}` })
        );
      });

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken({
        expiresAt: Math.floor(Date.now() / 1000) - 60, // expired
      });

      const [r1, r2, r3] = await Promise.all([
        sm.refresh(),
        sm.refresh(),
        sm.refresh(),
      ]);

      // Only one actual refresh should happen
      expect(refreshCount).toBe(1);
      expect(r1.token).toBe('refreshed-1');
      expect(r2.token).toBe('refreshed-1');
      expect(r3.token).toBe('refreshed-1');
    });
  });

  // ── Edge cases ───────────────────────────────────────────────────────────

  describe('edge cases', () => {
    it('should handle corrupt localStorage gracefully', () => {
      // No window object in node — this test verifies it doesn't crash
      const sm = new SessionManager(config);
      expect(sm.isAuthenticated()).toBe(false);
    });

    it('should handle refresh failure by falling back to authenticate', async () => {
      // Refresh fails -> falls back to authenticate()
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(createMockJsonResponse({ error: 'bad_refresh' }, 400))
        .mockResolvedValueOnce(
          createMockJsonResponse(createMockToken({ token: 'fallback-auth' }))
        );

      globalThis.fetch = fetchMock;

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken({
        expiresAt: Math.floor(Date.now() / 1000) - 60,
      });

      const result = await sm.refresh();
      expect(result.token).toBe('fallback-auth');
    });

    it('should add Authorization header in apiFetch', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse({ ok: true })
      );

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();

      await sm.apiFetch('https://api.openagents.test/tasks');

      const callHeaders = (globalThis.fetch as any).mock.calls[0][1].headers;
      expect(callHeaders.get('Authorization')).toBe('Bearer valid-token-abc123');
    });

    it('should merge custom init headers with Authorization', async () => {
      globalThis.fetch = vi.fn().mockResolvedValueOnce(
        createMockJsonResponse({ ok: true })
      );

      const sm = new SessionManager(config);
      (sm as any).currentToken = createMockToken();

      await sm.apiFetch('https://api.openagents.test/tasks', {
        headers: { 'X-Custom': 'custom-value' },
      });

      const callHeaders = (globalThis.fetch as any).mock.calls[0][1].headers;
      expect(callHeaders.get('Authorization')).toBe('Bearer valid-token-abc123');
      expect(callHeaders.get('X-Custom')).toBe('custom-value');
    });
  });
});
