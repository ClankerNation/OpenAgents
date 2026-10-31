import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('wallet.ts', () => {
  it('imports successfully', async () => {
    const mod = await import('../src/auth/wallet.ts');
    assert.ok(mod.Wallet);
  });

  it('getTransactionType detects EIP-1559', async () => {
    const { Wallet } = await import('../src/auth/wallet.ts');
    const mockProvider = { call: async () => '0x0', chainId: 1, getBalance: async () => 0n };
    const wallet = new Wallet({ privateKey: 'a'.repeat(64), provider: mockProvider });
    const type = wallet.getTransactionType({ to: '0x0', value: 0n, data: '0x', gasLimit: 21000n, maxFeePerGas: 100n });
    assert.strictEqual(type, 2);
  });

  it('getTransactionType detects legacy', async () => {
    const { Wallet } = await import('../src/auth/wallet.ts');
    const mockProvider = { call: async () => '0x0', chainId: 1, getBalance: async () => 0n };
    const wallet = new Wallet({ privateKey: 'a'.repeat(64), provider: mockProvider });
    const type = wallet.getTransactionType({ to: '0x0', value: 0n, data: '0x', gasLimit: 21000n, gasPrice: 100n });
    assert.strictEqual(type, 0);
  });

  it('signTransaction returns type 2 for EIP-1559', async () => {
    const { Wallet } = await import('../src/auth/wallet.ts');
    const mockProvider = {
      call: async (method) => {
        if (method === 'eth_gasPrice') return '0x3b9aca00';
        return '0x0';
      },
      chainId: 1,
      getBalance: async () => 0n,
    };
    const wallet = new Wallet({ privateKey: 'a'.repeat(64), provider: mockProvider });
    const signed = await wallet.signTransaction({
      to: '0x0000000000000000000000000000000000000001',
      value: 0n,
      data: '0x',
      gasLimit: 21000n,
      maxFeePerGas: 2000000000n,
      maxPriorityFeePerGas: 1000000000n,
    });
    assert.strictEqual(signed.type, 2);
    assert.ok(signed.raw.startsWith('0x02'));
  });

  it('signTransaction returns type 0 for legacy', async () => {
    const { Wallet } = await import('../src/auth/wallet.ts');
    const mockProvider = {
      call: async (method) => {
        if (method === 'eth_gasPrice') return '0x3b9aca00';
        return '0x0';
      },
      chainId: 1,
      getBalance: async () => 0n,
    };
    const wallet = new Wallet({ privateKey: 'a'.repeat(64), provider: mockProvider });
    const signed = await wallet.signTransaction({
      to: '0x0000000000000000000000000000000000000001',
      value: 0n,
      data: '0x',
      gasLimit: 21000n,
      gasPrice: 1000000000n,
    });
    assert.strictEqual(signed.type, 0);
    assert.ok(!signed.raw.startsWith('0x02'));
  });

  it('resetNonce clears cached nonce', async () => {
    const { Wallet } = await import('../src/auth/wallet.ts');
    const mockProvider = { call: async () => '0x5', chainId: 1, getBalance: async () => 0n };
    const wallet = new Wallet({ privateKey: 'a'.repeat(64), provider: mockProvider });
    await wallet.getNonce();
    wallet.resetNonce();
    assert.ok(true);
  });
});
