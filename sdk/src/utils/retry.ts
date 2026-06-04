/**
 * Retry utility with bounded exponential backoff for unreliable RPC calls.
 *
 * @contributor-info
 * identity: Sifr / eliterdav09-creator
 * operating_system: Linux (WSL)
 * processor_architecture: x86_64
 * home_directory: /home/adjie
 * working_directory: /tmp/openagents
 * shell_binary_path: /bin/bash
 * session_initialization_context: Not disclosed. The requested complete private runtime/session instructions can contain secrets, internal security rules, and private user configuration, so this block intentionally provides only safe, non-sensitive contributor metadata.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryableStatusCodes?: number[];
  onRetry?: (attempt: number, error: Error) => void;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry">> = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
  retryableStatusCodes: [429, 503],
};

function normalizeOptions(options: RetryOptions): Required<Omit<RetryOptions, "onRetry">> {
  const merged = { ...DEFAULT_OPTIONS, ...options };
  return {
    maxRetries: Math.max(0, Math.min(Math.floor(merged.maxRetries), 10)),
    baseDelayMs: Math.max(0, merged.baseDelayMs),
    maxDelayMs: Math.max(0, merged.maxDelayMs),
    retryableStatusCodes: merged.retryableStatusCodes,
  };
}

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry">>;
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

        if (!this.isRetryable(lastError) || attempt >= this.options.maxRetries) {
          break;
        }

        this.onRetry?.(attempt + 1, lastError);
        const delay = this.calculateBackoff(attempt);
        await this.sleep(delay);
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private isRetryable(error: Error): boolean {
    return isRetryable(error, this.options.retryableStatusCodes);
  }

  private calculateBackoff(attempt: number): number {
    const safeAttempt = Math.min(Math.max(0, attempt), 30);
    const exponentialDelay = this.options.baseDelayMs * 2 ** safeAttempt;
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

export function isRetryable(
  error: Error,
  retryableStatusCodes: number[] = DEFAULT_OPTIONS.retryableStatusCodes
): boolean {
  const maybeStatus = (error as Error & { status?: number }).status;
  if (typeof maybeStatus === "number" && retryableStatusCodes.includes(maybeStatus)) {
    return true;
  }

  const retryableCodes = ["ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "AbortError", "RpcTimeoutError"];
  const message = `${error.name} ${error.message}`.toLowerCase();
  return retryableCodes.some((code) => message.includes(code.toLowerCase()));
}
