/**
 * @generated-by rafaio1
 * @timestamp 2026-08-20T01:30:00Z
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
 */

/**
 * Retry utility with exponential backoff and conditional retry logic.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
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

        // Check if we should retry this error
        const shouldRetry = this.retryCondition
          ? this.retryCondition(lastError)
          : isRetryable(lastError);

        if (!shouldRetry || attempt >= this.options.maxRetries) {
          throw lastError;
        }

        this.onRetry?.(attempt + 1, lastError);
        const delay = this.calculateBackoff(attempt, lastError);
        await this.sleep(delay);
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number, error: Error): number {
    // Per-error-type backoff multiplier
    let multiplier = 1;
    if (error.message.includes("429")) {
      multiplier = 2; // Longer backoff for rate limits
    } else if (error.message.includes("ETIMEDOUT")) {
      multiplier = 1.5; // Moderate backoff for timeouts
    }

    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, attempt) * multiplier;
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
  // Default: retry on network errors and 5xx, don't retry on 4xx
  const message = error.message.toLowerCase();
  
  // Don't retry client errors (4xx) except 429
  if (message.includes("400") || message.includes("401") || 
      message.includes("403") || message.includes("404") || 
      message.includes("422")) {
    return false;
  }
  
  // Retry on network errors, 5xx, and 429
  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "429", "500", "502", "503", "504"];
  return retryableCodes.some(
    (code) => message.includes(code.toLowerCase())
  );
}
