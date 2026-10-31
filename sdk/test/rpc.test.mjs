import { describe, it } from 'node:test';
import assert from 'node:assert';

describe('rpc.ts', () => {
  describe('RpcProvider', () => {
    it('getChainId returns configured chain id', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      assert.strictEqual(provider.getChainId(), 1);
    });

    it('batchCall throws on empty... no, handles empty', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      // Mock fetch
      const origFetch = globalThis.fetch;
      globalThis.fetch = async () => ({
        json: async () => [],
      });
      const result = await provider.batchCall([]);
      assert.deepStrictEqual(result, []);
      globalThis.fetch = origFetch;
    });

    it('batchCall throws on oversized batch', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1, maxBatchSize: 2 });
      await assert.rejects(
        provider.batchCall([
          { method: 'eth_blockNumber', params: [] },
          { method: 'eth_blockNumber', params: [] },
          { method: 'eth_blockNumber', params: [] },
        ]),
        /exceeds max/
      );
    });

    it('batchCall matches responses by id', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const origFetch = globalThis.fetch;
      // Return responses in reverse order with different ids
      globalThis.fetch = async (_url, opts) => {
        const body = JSON.parse(opts.body);
        // Respond in reverse order
        const responses = body.map((r, i) => ({
          jsonrpc: '2.0',
          id: body[body.length - 1 - i].id,
          result: `result-${body.length - 1 - i}`,
        }));
        return {
          json: async () => responses,
        };
      };
      const result = await provider.batchCall([
        { method: 'm1', params: [] },
        { method: 'm2', params: [] },
      ]);
      // Results should be in original request order
      assert.strictEqual(result[0], 'result-0');
      assert.strictEqual(result[1], 'result-1');
      globalThis.fetch = origFetch;
    });

    it('batchCall handles partial failures', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const origFetch = globalThis.fetch;
      globalThis.fetch = async (_url, opts) => {
        const body = JSON.parse(opts.body);
        const responses = body.map((r, i) => {
          if (i === 1) {
            return { jsonrpc: '2.0', id: r.id, error: { code: -32000, message: 'fail' } };
          }
          return { jsonrpc: '2.0', id: r.id, result: `ok-${i}` };
        });
        return { json: async () => responses };
      };
      const result = await provider.batchCall([
        { method: 'm1', params: [] },
        { method: 'm2', params: [] },
      ]);
      assert.strictEqual(result[0], 'ok-0');
      assert.deepStrictEqual(result[1], { error: { code: -32000, message: 'fail' } });
      globalThis.fetch = origFetch;
    });

    it('batchCall handles missing responses', async () => {
      const { RpcProvider } = await import('../src/providers/rpc.ts');
      const provider = new RpcProvider({ url: 'http://localhost', chainId: 1 });
      const origFetch = globalThis.fetch;
      globalThis.fetch = async (_url, opts) => {
        const body = JSON.parse(opts.body);
        // Only respond to first request
        return { json: async () => [{ jsonrpc: '2.0', id: body[0].id, result: 'ok' }] };
      };
      const result = await provider.batchCall([
        { method: 'm1', params: [] },
        { method: 'm2', params: [] },
      ]);
      assert.strictEqual(result[0], 'ok');
      assert.strictEqual(result[1], null);
      globalThis.fetch = origFetch;
    });
  });
});
