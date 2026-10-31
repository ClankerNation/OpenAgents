/**
 * Contributor Metadata (required for bounty #137)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 */

/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 * Supports conditional retry based on error type.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  /**
   * Optional predicate that determines whether an error is retryable.
   * If provided, only errors for which this returns true will be retried.
   * If not provided, all errors are retried (default behavior).
   */
  retryCondition?: (error: Error) => boolean;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition">> = {
  maxRetries: 5,
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
        this.consecutiveFailures = 0; // Reset on success
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this.consecutiveFailures++;

        // Check if error is retryable based on condition
        const shouldRetry = this.retryCondition
          ? this.retryCondition(lastError)
          : true;

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
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, Math.min(attempt, 30));
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

export function isRetryable(error: Error): boolean {
  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "429"];
  const message = error.message.toLowerCase();
  return retryableCodes.some(
    (code) => message.includes(code.toLowerCase())
  );
}
