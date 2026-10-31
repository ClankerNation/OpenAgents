/**
 * Contributor Metadata (required for bounty #137)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  retryIf?: (error: Error) => boolean;
  shouldRetry?: (error: Error) => boolean;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryIf" | "shouldRetry">> = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryIf" | "shouldRetry">>;
  private onRetry?: (attempt: number, error: Error) => void;
  private retryIf?: (error: Error) => boolean;
  private shouldRetry?: (error: Error) => boolean;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.onRetry = options.onRetry;
    this.retryIf = options.retryIf;
    this.shouldRetry = options.shouldRetry;
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

        const retryPredicate = this.retryIf || this.shouldRetry;
        if (retryPredicate && !retryPredicate(lastError)) {
          throw lastError;
        }

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
    const cappedAttempt = Math.min(attempt, 10);
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, cappedAttempt);
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
