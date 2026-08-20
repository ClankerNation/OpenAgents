/**
 * @generated-by rafaio1
 * @timestamp 2026-08-20T13:05:00Z
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
 */

/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  retryCondition?: (error: Error) => boolean;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition">> = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

/**
 * Default retry condition: retry on network errors and 5xx, fail immediately on 4xx.
 */
function defaultRetryCondition(error: Error): boolean {
  const message = error.message.toLowerCase();
  
  // Network errors are always retryable
  const networkCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "ENOTFOUND", "EAI_AGAIN"];
  if (networkCodes.some(code => message.includes(code.toLowerCase()))) {
    return true;
  }
  
  // Extract HTTP status code if present in error message
  const statusMatch = message.match(/(?:status|code)[\s:=]*(\d{3})/i) || 
                      message.match(/(\d{3})/);
  if (statusMatch) {
    const status = parseInt(statusMatch[1], 10);
    // 4xx client errors should NOT be retried (except 429 rate limit)
    if (status >= 400 && status < 500 && status !== 429) {
      return false;
    }
    // 5xx server errors and 429 rate limits ARE retryable
    if (status >= 500 || status === 429) {
      return true;
    }
  }
  
  // Fallback: retry if it looks like a transient error
  return isRetryable(error);
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
        // Reset consecutive failures on success
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        
        // Check if this error type should be retried
        if (!this.retryCondition(lastError)) {
          throw lastError; // Fail immediately for non-retryable errors
        }
        
        this.consecutiveFailures++;

        if (attempt < this.options.maxRetries) {
          this.onRetry?.(attempt + 1, lastError);
          const delay = this.calculateBackoff(attempt, lastError);
          await this.sleep(delay);
        }
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number, error?: Error): number {
    // Cap exponent to prevent overflow (max 2^10 = 1024 multiplier)
    const exponent = Math.min(attempt, 10);
    let exponentialDelay = this.options.baseDelayMs * Math.pow(2, exponent);
    
    // Apply per-error-type backoff multiplier for rate limits
    if (error) {
      const message = error.message.toLowerCase();
      if (message.includes("429") || message.includes("rate limit")) {
        exponentialDelay *= 2; // Double backoff for rate limits
      }
    }
    
    const jitter = Math.random() * this.options.baseDelayMs * 0.5;
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
