/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  retryCondition?: (error: Error) => boolean;
  backoffMultiplier?: (error: Error) => number;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "backoffMultiplier">> = {
  maxRetries: Infinity, // BUG: No cap — will retry forever by default
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "backoffMultiplier">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private retryCondition: (error: Error) => boolean;
  private backoffMultiplier: (error: Error) => number;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.onRetry = options.onRetry;
    this.retryCondition = options.retryCondition ?? isRetryable;
    this.backoffMultiplier = options.backoffMultiplier ?? defaultBackoffMultiplier;
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
          const delay = this.calculateBackoff(attempt, lastError);
          await this.sleep(delay);
        } else {
          throw lastError;
        }
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number, error: Error): number {
    // BUG: 2 ** attempt overflows to Infinity for large attempt values (attempt > ~1023),
    // and Math.min with Infinity returns maxDelayMs, but intermediate calc can cause issues
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, attempt);
    const jitter = Math.random() * this.options.baseDelayMs;
    return Math.min((exponentialDelay + jitter) * this.backoffMultiplier(error), this.options.maxDelayMs);
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
  const status = getErrorStatus(error);
  if (status !== undefined) {
    if (status === 429) return true;
    if (status >= 400 && status < 500) return false;
    if (status >= 500 && status < 600) return true;
  }

  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "ECONNABORTED", "429", "fetch failed", "network"];
  const message = error.message.toLowerCase();
  return retryableCodes.some(
    (code) => message.includes(code.toLowerCase())
  );
}

export function defaultBackoffMultiplier(error: Error): number {
  const status = getErrorStatus(error);
  if (status === 429) return 2;
  if (status !== undefined && status >= 500) return 1.5;
  return 1;
}

function getErrorStatus(error: Error): number | undefined {
  const maybeStatus = (error as Error & { status?: unknown; statusCode?: unknown; code?: unknown }).status ??
    (error as Error & { statusCode?: unknown }).statusCode ??
    (error as Error & { code?: unknown }).code;

  if (typeof maybeStatus === "number") return maybeStatus;
  if (typeof maybeStatus === "string" && /^\d+$/.test(maybeStatus)) {
    return Number(maybeStatus);
  }

  const match = error.message.match(/\b([1-5]\d\d)\b/);
  return match ? Number(match[1]) : undefined;
}
