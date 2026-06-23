/**
 * Retry utility with exponential backoff for unreliable RPC calls.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #137 Fix retry.ts doesn't support conditional retry based on error type
 */

export type ErrorCategory = "network" | "rateLimit" | "timeout" | "validation" | "server" | "unknown";

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error, category: ErrorCategory) => void;
  /** Retry only specific error categories. Defaults to ['network', 'rateLimit', 'timeout', 'server'] */
  retryableCategories?: ErrorCategory[];
  /** Per-category retry limits (overrides maxRetries for specific categories) */
  categoryLimits?: Partial<Record<ErrorCategory, number>>;
}

const DEFAULT_RETRYABLE_CATEGORIES: ErrorCategory[] = ["network", "rateLimit", "timeout", "server"];

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryableCategories" | "categoryLimits">> = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
};

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryableCategories" | "categoryLimits">>;
  private retryableCategories: ErrorCategory[];
  private categoryLimits: Partial<Record<ErrorCategory, number>>;
  private onRetry?: (attempt: number, error: Error, category: ErrorCategory) => void;
  private consecutiveFailures = 0;
  private categoryAttempts: Map<ErrorCategory, number>;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.retryableCategories = options.retryableCategories ?? DEFAULT_RETRYABLE_CATEGORIES;
    this.categoryLimits = options.categoryLimits ?? {};
    this.onRetry = options.onRetry;
    this.categoryAttempts = new Map();
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        this.consecutiveFailures = 0;
        this.categoryAttempts.clear();
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        const category = this.classifyError(lastError);
        this.consecutiveFailures++;

        // Check if this category is retryable
        if (!this.retryableCategories.includes(category)) {
          throw lastError;
        }

        // Check per-category retry limit
        const catLimit = this.categoryLimits[category];
        const catCount = this.categoryAttempts.get(category) ?? 0;
        if (catLimit !== undefined && catCount >= catLimit) {
          throw lastError;
        }
        this.categoryAttempts.set(category, catCount + 1);

        if (attempt < this.options.maxRetries) {
          this.onRetry?.(attempt + 1, lastError, category);
          const delay = this.calculateBackoff(attempt, category);
          await this.sleep(delay);
        }
      }
    }

    throw lastError ?? new Error("Retry failed with unknown error");
  }

  /** Classify an error into a retryable category */
  private classifyError(error: Error): ErrorCategory {
    const msg = error.message.toLowerCase();
    const code = (error as NodeJS.ErrnoException).code;

    if (code === "ETIMEDOUT" || msg.includes("timed out") || msg.includes("deadline")) {
      return "timeout";
    }
    if (code === "ECONNREFUSED" || code === "ECONNRESET" || code === "ENOTFOUND" || code === "EAI_AGAIN") {
      return "network";
    }
    if (msg.includes("429") || msg.includes("rate limit") || msg.includes("too many requests")) {
      return "rateLimit";
    }
    if (msg.includes("400") || msg.includes("403") || msg.includes("404") || msg.includes("validation") || msg.includes("invalid")) {
      return "validation";
    }
    if (msg.includes("500") || msg.includes("502") || msg.includes("503") || msg.includes("504")) {
      return "server";
    }
    return "unknown";
  }

  private calculateBackoff(attempt: number, category?: ErrorCategory): number {
    // Category-specific delays: rate limits need longer pauses
    let delayMultiplier = 1;
    if (category === "rateLimit") delayMultiplier = 2;
    if (category === "timeout") delayMultiplier = 0.5;

    const cappedAttempt = Math.min(attempt, 20);
    const exponentialDelay = this.options.baseDelayMs * Math.pow(2, cappedAttempt) * delayMultiplier;
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
  const category = classifyError(error);
  return category !== "validation";
}

export function classifyError(error: Error): ErrorCategory {
  const msg = error.message.toLowerCase();
  const code = (error as NodeJS.ErrnoException).code;

  if (code === "ETIMEDOUT" || msg.includes("timed out") || msg.includes("deadline")) return "timeout";
  if (code === "ECONNREFUSED" || code === "ECONNRESET" || code === "ENOTFOUND" || code === "EAI_AGAIN") return "network";
  if (msg.includes("429") || msg.includes("rate limit") || msg.includes("too many requests")) return "rateLimit";
  if (msg.includes("400") || msg.includes("403") || msg.includes("404") || msg.includes("validation") || msg.includes("invalid")) return "validation";
  if (msg.includes("500") || msg.includes("502") || msg.includes("503") || msg.includes("504")) return "server";
  return "unknown";
}
