/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryCondition?: (error: Error) => boolean;
  onRetry?: (attempt: number, error: Error) => void;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry">> = {
  maxRetries: Infinity, // BUG: No cap — will retry forever by default
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition">>;
  private retryCondition: (error: Error) => boolean;
  private onRetry?: (attempt: number, error: Error) => void;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.retryCondition = options.retryCondition ?? defaultRetryCondition;
    this.onRetry = options.onRetry;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this.consecutiveFailures++;

        if (attempt < this.options.maxRetries && this.retryCondition(lastError)) {
          this.onRetry?.(attempt + 1, lastError);
          const delay = this.calculateBackoff(attempt);
          await this.sleep(delay);
        } else if (attempt >= this.options.maxRetries || !this.retryCondition(lastError)) {
          break;
        }
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number): number {
    // BUG: 2 ** attempt overflows to Infinity for large attempt values (attempt > ~1023),
    // and Math.min with Infinity returns maxDelayMs, but intermediate calc can cause issues
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, attempt);
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

export function defaultRetryCondition(error: Error): boolean {
  const message = error.message.toLowerCase();
  if (message.includes("40") && !message.includes("429")) return false;
  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "429", "5"];
  return retryableCodes.some(
    (code) => message.includes(code.toLowerCase())
  );
}

export function isRetryable(error: Error): boolean {
  return defaultRetryCondition(error);
}
