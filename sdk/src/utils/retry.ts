/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry">> = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 60_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = {
      maxRetries: normalizeNonNegativeInteger(
        options.maxRetries,
        DEFAULT_OPTIONS.maxRetries
      ),
      baseDelayMs: normalizeNonNegativeNumber(
        options.baseDelayMs,
        DEFAULT_OPTIONS.baseDelayMs
      ),
      maxDelayMs: normalizeNonNegativeNumber(
        options.maxDelayMs,
        DEFAULT_OPTIONS.maxDelayMs
      ),
    };
    this.onRetry = options.onRetry;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        this.reset();
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
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
    const safeAttempt = Math.min(
      Math.max(0, Math.floor(attempt)),
      31
    );
    const exponentialDelay = this.options.baseDelayMs * (2 ** safeAttempt);
    const cappedDelay = Math.min(exponentialDelay, this.options.maxDelayMs);
    const jitter = cappedDelay * Math.random() * 0.25;
    return Math.min(cappedDelay + jitter, this.options.maxDelayMs);
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

function normalizeNonNegativeInteger(
  value: number | undefined,
  fallback: number
): number {
  if (value === undefined || !Number.isFinite(value) || value < 0) {
    return fallback;
  }

  return Math.floor(value);
}

function normalizeNonNegativeNumber(
  value: number | undefined,
  fallback: number
): number {
  if (value === undefined || !Number.isFinite(value) || value < 0) {
    return fallback;
  }

  return value;
}
