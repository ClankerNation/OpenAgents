import { describe, it } from 'node:test';
import assert from 'node:assert';

// Mock wallet
const mockWallet = {
  address: '0x1234567890abcdef1234567890abcdef12345678',
  sendTransaction: async () => '0xmocksignature',
};

describe('session.ts', () => {
  describe('AuthenticationError', () => {
    it('creates error with correct name', async () => {
      const { AuthenticationError } = await import('../src/auth/session.ts');
      const err = new AuthenticationError('test');
      assert.strictEqual(err.name, 'AuthenticationError');
      assert.strictEqual(err.message, 'test');
    });
  });

  describe('SessionManager', () => {
    it('isTokenExpired returns true for expired token', async () => {
      const { SessionManager } = await import('../src/auth/session.ts');
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'http://localhost' });
      const expiredToken = { token: 'abc', expiresAt: 0, refreshToken: 'ref', walletAddress: '0x123' };
      assert.strictEqual((sm).isTokenExpired(expiredToken), true);
    });

    it('isTokenExpired returns false for valid token', async () => {
      const { SessionManager } = await import('../src/auth/session.ts');
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'http://localhost' });
      const futureToken = { token: 'abc', expiresAt: Math.floor(Date.now() / 1000) + 3600, refreshToken: 'ref', walletAddress: '0x123' };
      assert.strictEqual((sm).isTokenExpired(futureToken), false);
    });

    it('isAuthenticated returns false initially', async () => {
      const { SessionManager } = await import('../src/auth/session.ts');
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'http://localhost' });
      assert.strictEqual(sm.isAuthenticated(), false);
    });

    it('logout clears state', async () => {
      const { SessionManager } = await import('../src/auth/session.ts');
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'http://localhost' });
      (sm).currentToken = { token: 'abc', expiresAt: 9999999999, refreshToken: 'ref', walletAddress: '0x123' };
      sm.logout();
      assert.strictEqual(sm.isAuthenticated(), false);
    });

    it('autoRefresh defaults to true', async () => {
      const { SessionManager } = await import('../src/auth/session.ts');
      const sm = new SessionManager({ wallet: mockWallet, apiBaseUrl: 'http://localhost' });
      assert.strictEqual((sm).autoRefresh, true);
    });
  });
});
