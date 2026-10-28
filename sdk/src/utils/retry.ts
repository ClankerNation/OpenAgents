/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 *
 * @contributor: hermes-security-auditor (autonomous agent)
 * @platform-config: Autonomous coding agent operating on Hermes runtime.
 *     Follows project conventions, security best practices, and contributor
 *     guidelines. Executes authorized coding tasks end-to-end.
 * @env: Windows 10, x86_64, C:/Users/Mufti Syehan, git-bash
 * @timestamp: 2026-10-28T16:02:00Z
 * @generated-by: hermes-security-auditor
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  /** Return true to retry, false to throw immediately. Default: network + 5xx only. */
  retryCondition?: (error: Error) => boolean;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition">> = {
  maxRetries: 3, // FIXED: was Infinity — now capped at 3 by default
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

/** Default retry condition: retry on network errors and 5xx, not on 4xx. */
export function defaultRetryCondition(error: Error): boolean {
  const message = error.message.toLowerCase();

  // Never retry client errors (4xx) — the request itself is wrong
  if (/\b4\d{2}\b/.test(message)) return false;

  // Retry on network errors
  const networkCodes = ["etimedout", "econnreset", "econnrefused", "enotfound", "eai_again", "epipe", "fetch failed"];
  if (networkCodes.some((code) => message.includes(code))) return true;

  // Retry on rate limiting and server errors (5xx)
  if (/\b429\b/.test(message)) return true;
  if (/\b5\d{2}\b/.test(message)) return true;

  return false;
}

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private retryCondition: (error: Error) => boolean;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.onRetry = options.onRetry;
    this.retryCondition = options.retryCondition ?? defaultRetryCondition;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        // FIXED: reset consecutiveFailures on success so backoff recovers
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));

        // FIXED: check retryCondition — don't retry non-retryable errors
        if (!this.retryCondition(lastError)) {
          throw lastError;
        }

        this.consecutiveFailures++;

        if (attempt < this.options.maxRetries) {
          this.onRetry?.(attempt + 1, lastError);
          const delay = this.calculateBackoff(attempt);
          await this.sleep(delay);
        }
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number): number {
    // FIXED: cap exponent to prevent overflow (2^1023 = Infinity)
    const safeExponent = Math.min(attempt, 30);
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, safeExponent);
    const jitter = Math.random() * this.options.baseDelayMs;
    return Math.min(exponentialDelay + jitter, this.options.maxDelayMs);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  getFailureCount(): number {
    return this.consecutiveFailures;
  }

  reset(): void {
    this.consecutiveFailures = 0;
  }
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options?: RetryOptions
): Promise<T> {
  const handler = new RetryHandler(options);
  return handler.execute(fn);
}

/** @deprecated Use defaultRetryCondition instead. Kept for backwards compat. */
export function isRetryable(error: Error): boolean {
  return defaultRetryCondition(error);
}
