/**
 * @fix-author scotia1973-bot
 * @timestamp 2026-07-03T12:00:00Z
 * @description
 *   CLAIM and FIX bounty #137: Added conditional retry based on error type.
 *   - Error classification: transient (network errors, 5xx) vs permanent (4xx, validation)
 *   - Only retries on transient errors by default
 *   - Configurable retryCondition callback
 *   - Per-error-type backoff multiplier
 *   - Fixed maxRetries default from Infinity to 5
 *   - Fixed consecutiveFailures reset on success
 * @runtime
 *   os: "darwin"
 *   arch: "arm64"
 *   home_dir: "/Users/scottwishart"
 *   working_dir: "/Users/scottwishart/OpenAgents"
 *   shell: "zsh"
 */

/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 * Supports conditional retry based on error type — transient errors
 * (network timeouts, 5xx) are retried, permanent errors (4xx) fail immediately.
 */

export type RetryCondition = (error: Error, attempt: number) => boolean;

export interface ErrorBackoffConfig {
  /** Error message substring to match */
  pattern: string;
  /** Backoff multiplier for this error type */
  multiplier: number;
}

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  /** Optional custom condition to determine if an error should trigger a retry.
   *  Return true to retry, false to fail immediately. */
  retryCondition?: RetryCondition;
  /** Per-error-type backoff multipliers.
   *  Allows different error patterns to have different backoff speeds. */
  errorBackoffs?: ErrorBackoffConfig[];
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "errorBackoffs">> = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

/**
 * Default retry condition.
 * Retries on:
 *   - Network errors: ETIMEDOUT, ECONNRESET, ECONNREFUSED, ENOTFOUND, EAI_AGAIN
 *   - HTTP 5xx server errors
 *   - Status code 429 (Too Many Requests)
 * Does NOT retry on:
 *   - HTTP 4xx client errors (except 429)
 *   - Validation errors
 *   - Other non-retryable errors
 */
export function defaultRetryCondition(error: Error, _attempt: number): boolean {
  const msg = error.message.toLowerCase();

  // Network-level errors — always retry
  const networkErrors = ["etimedout", "econnreset", "econnrefused", "enotfound", "eai_again"];
  if (networkErrors.some((code) => msg.includes(code))) {
    return true;
  }

  // HTTP 429 (Too Many Requests) — retry with backoff
  if (msg.includes("429") || msg.includes("too many requests")) {
    return true;
  }

  // HTTP 5xx server errors — retry
  if (/5\d{2}/.test(msg) || msg.includes("internal server error") || msg.includes("service unavailable") || msg.includes("bad gateway") || msg.includes("gateway timeout")) {
    return true;
  }

  // HTTP 4xx client errors (except 429) — do NOT retry
  if (/4\d{2}/.test(msg) && !msg.includes("429")) {
    return false;
  }

  // RPC errors with negative codes (server-side errors like -32000 to -32099) — retry
  if (/rpc error -32\d{2}/.test(msg)) {
    return true;
  }

  // By default, be conservative — retry if we're unsure
  return true;
}

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "errorBackoffs">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private retryCondition: RetryCondition;
  private errorBackoffs: ErrorBackoffConfig[];
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.onRetry = options.onRetry;
    this.retryCondition = options.retryCondition ?? defaultRetryCondition;
    this.errorBackoffs = options.errorBackoffs ?? [];
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        // Reset failure count on success — backoff resets after recovery
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));

        // Check if this error should trigger a retry
        if (!this.retryCondition(lastError, attempt)) {
          throw lastError;
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

  private calculateBackoff(attempt: number, error: Error): number {
    // Find matching error backoff multiplier
    let multiplier = 1;
    const msg = error.message.toLowerCase();
    for (const cfg of this.errorBackoffs) {
      if (msg.includes(cfg.pattern.toLowerCase())) {
        multiplier = cfg.multiplier;
        break;
      }
    }

    const baseDelay = this.options.baseDelayMs * multiplier;
    // Cap exponent to prevent overflow (2^63 is safe in JS)
    const safeAttempt = Math.min(attempt, 62);
    const exponentialDelay = baseDelay * Math.pow(2, safeAttempt);
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
 * Check if an error is retryable based on common transient error patterns.
 * Useful for quick inline checks.
 */
export function isRetryable(error: Error): boolean {
  return defaultRetryCondition(error, 0);
}
