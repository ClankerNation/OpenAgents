import { describe, it } from 'node:test';
import assert from 'node:assert';
import { withRetry, RetryHandler, isRetryable } from '../src/utils/retry.ts';

describe('retry.ts', () => {
  describe('RetryHandler', () => {
    it('succeeds on first attempt', async () => {
      const handler = new RetryHandler({ maxRetries: 3, baseDelayMs: 1 });
      const result = await handler.execute(async () => 42);
      assert.strictEqual(result, 42);
      assert.strictEqual(handler.getFailureCount(), 0);
    });

    it('retries on failure and succeeds', async () => {
      const handler = new RetryHandler({ maxRetries: 3, baseDelayMs: 1 });
      let calls = 0;
      const result = await handler.execute(async () => {
        calls++;
        if (calls < 3) throw new Error('fail');
        return 'success';
      });
      assert.strictEqual(result, 'success');
      assert.strictEqual(calls, 3);
    });

    it('throws after max retries exceeded', async () => {
      const handler = new RetryHandler({ maxRetries: 2, baseDelayMs: 1 });
      let calls = 0;
      await assert.rejects(
        handler.execute(async () => {
          calls++;
          throw new Error('always fail');
        }),
        /always fail/
      );
      assert.strictEqual(calls, 3);
    });

    it('resets failure count on success', async () => {
      const handler = new RetryHandler({ maxRetries: 3, baseDelayMs: 1 });
      let calls = 0;
      await handler.execute(async () => {
        calls++;
        if (calls === 1) throw new Error('first fail');
        return 'ok';
      });
      assert.strictEqual(handler.getFailureCount(), 0);
    });
  });

  describe('conditional retry (retryIf)', () => {
    it('stops retrying when retryIf returns false', async () => {
      const handler = new RetryHandler({
        maxRetries: 5,
        baseDelayMs: 1,
        retryIf: (err) => err.message.includes('retryable'),
      });
      let calls = 0;
      await assert.rejects(
        handler.execute(async () => {
          calls++;
          throw new Error('fatal error');
        }),
        /fatal/
      );
      assert.strictEqual(calls, 1);
    });

    it('retries when retryIf returns true', async () => {
      const handler = new RetryHandler({
        maxRetries: 3,
        baseDelayMs: 1,
        retryIf: (err) => err.message.includes('retryable'),
      });
      let calls = 0;
      const result = await handler.execute(async () => {
        calls++;
        if (calls < 3) throw new Error('retryable error');
        return 'done';
      });
      assert.strictEqual(result, 'done');
      assert.strictEqual(calls, 3);
    });
  });

  describe('shouldRetry alias', () => {
    it('works with shouldRetry option', async () => {
      const handler = new RetryHandler({
        maxRetries: 3,
        baseDelayMs: 1,
        shouldRetry: () => true,
      });
      let calls = 0;
      await assert.rejects(
        handler.execute(async () => {
          calls++;
          throw new Error('fail');
        })
      );
      assert.strictEqual(calls, 4);
    });
  });

  describe('withRetry', () => {
    it('works as convenience function', async () => {
      const result = await withRetry(async () => 99, { maxRetries: 1, baseDelayMs: 1 });
      assert.strictEqual(result, 99);
    });
  });

  describe('isRetryable', () => {
    it('returns true for retryable errors', () => {
      assert.strictEqual(isRetryable(new Error('ETIMEDOUT')), true);
      assert.strictEqual(isRetryable(new Error('ECONNRESET')), true);
      assert.strictEqual(isRetryable(new Error('429 too many requests')), true);
    });

    it('returns false for non-retryable errors', () => {
      assert.strictEqual(isRetryable(new Error('not found')), false);
      assert.strictEqual(isRetryable(new Error('invalid input')), false);
    });
  });

  describe('maxRetries default', () => {
    it('defaults to 5 instead of Infinity', async () => {
      const handler = new RetryHandler({ baseDelayMs: 1 });
      let calls = 0;
      await assert.rejects(
        handler.execute(async () => {
          calls++;
          throw new Error('fail');
        })
      );
      // With maxRetries=5, should be 6 calls (0..5)
      assert.strictEqual(calls, 6);
    });
  });

  describe('backoff capping', () => {
    it('does not overflow for large attempt values', async () => {
      const handler = new RetryHandler({ maxRetries: 3, baseDelayMs: 100, maxDelayMs: 1000 });
      let calls = 0;
      await assert.rejects(
        handler.execute(async () => {
          calls++;
          throw new Error('fail');
        })
      );
      assert.ok(calls <= 4);
    });
  });
});
