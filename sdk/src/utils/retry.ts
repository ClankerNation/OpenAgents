// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

/**
 * Retry utility with exponential backoff and conditional retry logic.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  /** Custom condition to determine if an error is retryable. Return true to retry. */
  retryCondition?: (error: Error) => boolean;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition">> = {
  maxRetries: 5, // Safe default cap instead of Infinity
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private retryCondition?: (error: Error) => boolean;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.onRetry = options.onRetry;
    this.retryCondition = options.retryCondition;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        // Reset failure counter on success
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this.consecutiveFailures++;

        // Check if we should retry this error
        const shouldRetry = this.retryCondition
          ? this.retryCondition(lastError)
          : isRetryable(lastError);

        if (!shouldRetry || attempt >= this.options.maxRetries) {
          throw lastError;
        }

        this.onRetry?.(attempt + 1, lastError);
        const delay = this.calculateBackoff(attempt);
        await this.sleep(delay);
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number): number {
    // Cap exponent to prevent overflow (2^30 is already ~1 billion ms)
    const exponent = Math.min(attempt, 30);
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, exponent);
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

/**
 * Default retryability check: retries network errors and 5xx, rejects 4xx.
 * HTTP status codes are extracted from error messages or properties.
 */
export function isRetryable(error: Error): boolean {
  const message = error.message.toLowerCase();

  // Network-level errors are always retryable
  const networkCodes = ["etimedout", "econnreset", "econnrefused", "enotfound", "eai_again"];
  if (networkCodes.some((code) => message.includes(code))) {
    return true;
  }

  // Extract HTTP status code from error
  const statusMatch = message.match(/\b(\d{3})\b/);
  if (statusMatch) {
    const status = parseInt(statusMatch[1], 10);
    // 4xx client errors are NOT retryable (except 429 rate limit)
    if (status >= 400 && status < 500 && status !== 429) {
      return false;
    }
    // 5xx server errors and 429 are retryable
    if (status >= 500 || status === 429) {
      return true;
    }
  }

  // Rate limiting keywords
  if (message.includes("rate limit") || message.includes("too many requests")) {
    return true;
  }

  // Default: retry unknown errors (conservative approach)
  return true;
}
