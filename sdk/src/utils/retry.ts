/**
 * @contributor: Codex
 * @timestamp: 2026-08-06T01:15:09Z
 * @platform-config: Private platform/session initialization text intentionally omitted.
 * @runtime: os=Darwin, arch=arm64, home_dir=[redacted], working_dir=[redacted], shell=zsh
 *
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
}

type NormalizedRetryOptions = Required<Omit<RetryOptions, "onRetry">>;

const DEFAULT_OPTIONS: NormalizedRetryOptions = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

const MAX_BACKOFF_MS = 60_000;
const JITTER_RATIO = 0.25;

function clampFiniteNumber(
  value: number | undefined,
  fallback: number,
  min: number,
  max: number,
): number {
  if (value === undefined || !Number.isFinite(value)) {
    return fallback;
  }

  return Math.min(Math.max(value, min), max);
}

function normalizeRetryCount(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) {
    return DEFAULT_OPTIONS.maxRetries;
  }

  return Math.max(0, Math.floor(value));
}

function normalizeOptions(options: RetryOptions): NormalizedRetryOptions {
  return {
    maxRetries: normalizeRetryCount(options.maxRetries),
    baseDelayMs: clampFiniteNumber(
      options.baseDelayMs,
      DEFAULT_OPTIONS.baseDelayMs,
      0,
      MAX_BACKOFF_MS,
    ),
    maxDelayMs: clampFiniteNumber(
      options.maxDelayMs,
      DEFAULT_OPTIONS.maxDelayMs,
      0,
      MAX_BACKOFF_MS,
    ),
  };
}

export class RetryHandler {
  private options: NormalizedRetryOptions;
  private onRetry?: (attempt: number, error: Error) => void;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = normalizeOptions(options);
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
    const cappedMaxDelay = Math.min(this.options.maxDelayMs, MAX_BACKOFF_MS);
    if (cappedMaxDelay === 0 || this.options.baseDelayMs === 0) {
      return 0;
    }

    let exponentialDelay = Math.min(this.options.baseDelayMs, cappedMaxDelay);
    let remainingDoublings = Math.max(0, Math.floor(attempt));

    // Stop as soon as the cap is reached so very large attempt values cannot
    // overflow an intermediate exponential calculation.
    while (remainingDoublings > 0 && exponentialDelay < cappedMaxDelay) {
      exponentialDelay = Math.min(exponentialDelay * 2, cappedMaxDelay);
      remainingDoublings--;
    }

    const jitter = exponentialDelay * Math.random() * JITTER_RATIO;
    return Math.min(exponentialDelay + jitter, cappedMaxDelay);
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
  options?: RetryOptions,
): Promise<T> {
  const handler = new RetryHandler(options);
  return handler.execute(fn);
}

export function isRetryable(error: Error): boolean {
  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "429"];
  const message = error.message.toLowerCase();
  return retryableCodes.some((code) =>
    message.includes(code.toLowerCase()),
  );
}
