/**
 * @generated-by
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T12:00:00Z
 * platform_config: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: {"os":"win32","arch":"x64","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 *
 * Retry utility with conditional retry, exponential backoff, and per-error-type backoff multipliers.
 */

const DEFAULT_RETRYABLE_CODES = new Set([
  "ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "EAI_AGAIN",
  "ENOTFOUND", "ENETUNREACH", "EPIPE",
]);

const DEFAULT_RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryCondition?: (error: Error) => boolean;
  onRetry?: (attempt: number, error: Error) => void;
  backoffMultiplier?: number;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition">> = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
  backoffMultiplier: 2,
};

function defaultRetryCondition(error: Error): boolean {
  if (DEFAULT_RETRYABLE_CODES.has(error.message)) return true;

  const msg = error.message.toLowerCase();
  for (const code of DEFAULT_RETRYABLE_STATUS) {
    if (msg.includes(String(code))) return true;
  }
  if (msg.includes("timeout") || msg.includes("timed out")) return true;
  if (msg.includes("5xx") || /5\d{2}/.test(msg)) return true;

  if (/4[0-8]\d/.test(msg) || msg.includes("4xx")) return false;
  if (msg.includes("400") || msg.includes("bad request")) return false;
  if (msg.includes("401") || msg.includes("unauthorized")) return false;
  if (msg.includes("403") || msg.includes("forbidden")) return false;
  if (msg.includes("404") || msg.includes("not found")) return false;
  if (msg.includes("422") || msg.includes("unprocessable")) return false;

  return true;
}

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

    const maxAttempts = Math.min(this.options.maxRetries, 10);
    for (let attempt = 0; attempt <= maxAttempts; attempt++) {
      try {
        const result = await fn();
        this.consecutiveFailures = 0;
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this.consecutiveFailures++;

        const shouldRetry = this.retryCondition(lastError);
        if (!shouldRetry || attempt >= maxAttempts) {
          throw lastError;
        }

        this.onRetry?.(attempt + 1, lastError);
        const delay = this.calculateBackoff(attempt);
        await this.sleep(delay);
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  private calculateBackoff(attempt: number): number {
    const cap = Math.min(attempt, 32);
    let delay = this.options.baseDelayMs;
    for (let i = 0; i < cap; i++) {
      delay *= this.options.backoffMultiplier;
      if (delay >= this.options.maxDelayMs) {
        delay = this.options.maxDelayMs;
        break;
      }
    }
    const jitter = Math.random() * this.options.baseDelayMs;
    return Math.min(delay + jitter, this.options.maxDelayMs);
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
  return defaultRetryCondition(error);
}
