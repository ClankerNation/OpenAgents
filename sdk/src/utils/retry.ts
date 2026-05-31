/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 *
 * @generated-by Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, home C:/Users/55093, working directory F:/jiedan/OpenAgents-bounty-run, shell PowerShell 7.6.2
 * @timestamp 2026-05-31T00:00:00-07:00
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryCondition?: (error: Error) => boolean;
  backoffMultiplier?: (error: Error) => number;
  onRetry?: (attempt: number, error: Error) => void;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "backoffMultiplier">> = {
  maxRetries: Infinity, // BUG: No cap — will retry forever by default
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "backoffMultiplier">>;
  private retryCondition: (error: Error) => boolean;
  private backoffMultiplier: (error: Error) => number;
  private onRetry?: (attempt: number, error: Error) => void;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.retryCondition = options.retryCondition ?? isRetryable;
    this.backoffMultiplier = options.backoffMultiplier ?? defaultBackoffMultiplier;
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

        if (attempt >= this.options.maxRetries || !this.retryCondition(lastError)) {
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
    // BUG: 2 ** attempt overflows to Infinity for large attempt values (attempt > ~1023),
    // and Math.min with Infinity returns maxDelayMs, but intermediate calc can cause issues
    const multiplier = Math.max(0, this.backoffMultiplier(error));
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
  const status = getErrorStatus(error);
  if (status !== undefined) {
    return status >= 500;
  }

  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "ENOTFOUND", "EAI_AGAIN"];
  const message = error.message.toLowerCase();
  return retryableCodes.some((code) => message.includes(code.toLowerCase()));
}

function defaultBackoffMultiplier(error: Error): number {
  const status = getErrorStatus(error);
  if (status !== undefined && status >= 500) {
    return 2;
  }
  return 1;
}

function getErrorStatus(error: Error): number | undefined {
  const maybeStatus = (error as Error & { status?: unknown; statusCode?: unknown; code?: unknown });
  const status = maybeStatus.status ?? maybeStatus.statusCode ?? maybeStatus.code;
  if (typeof status === "number") {
    return status;
  }
  if (typeof status === "string" && /^\d{3}$/.test(status)) {
    return Number(status);
  }

  const match = error.message.match(/\b([45]\d{2})\b/);
  return match ? Number(match[1]) : undefined;
}
