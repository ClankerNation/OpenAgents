/**
 * @generated-by
 * name: oocheol
 * timestamp: 2026-05-19T04:00:00Z
 * platform_instructions: Gemini CLI engineering agent. Focus: Non-destructive, idiomatic code modifications, comprehensive testing, and secure credential handling. Follows Research-Strategy-Execution lifecycle.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents","shell":"powershell"}
 *
 * Robust retry utility with conditional logic, exponential backoff, and per-error multipliers.
 */

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /**
   * Optional custom condition to determine if an error should be retried.
   * Returns true to retry, false to fail immediately.
   */
  retryCondition?: (error: Error) => boolean;
  /**
   * Optional callback triggered before each retry attempt.
   */
  onRetry?: (attempt: number, error: Error) => void;
  /**
   * Per-error-type backoff multiplier. 
   * Example: { '429': 4, '500': 2 }
   */
  multipliers?: Record<string, number>;
  /**
   * Default multiplier if error type not in multipliers map.
   */
  defaultMultiplier?: number;
}

const DEFAULT_OPTIONS: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "multipliers">> = {
  maxRetries: 5,
  baseDelayMs: 500,
  maxDelayMs: 60_000,
  defaultMultiplier: 2,
};

const NETWORK_ERROR_CODES = new Set([
  "ETIMEDOUT",
  "ECONNRESET",
  "ECONNREFUSED",
  "EAI_AGAIN",
  "ENOTFOUND",
  "ENETUNREACH",
  "EPIPE",
]);

function defaultRetryCondition(error: Error): boolean {
  const message = error.message.toLowerCase();
  
  // Retry on network error codes
  if (NETWORK_ERROR_CODES.has(error.message)) {
    return true;
  }

  const statusMatch = message.match(/\b(\d{3})\b/);
  const status = statusMatch ? parseInt(statusMatch[1], 10) : null;

  // Retry on 408 (Request Timeout), 429 (Too Many Requests) and 5xx (Server Errors)
  if (status === 408 || status === 429 || (status && status >= 500 && status <= 599)) {
    return true;
  }

  // Generic timeout keywords
  if (message.includes("timeout") || message.includes("timed out")) {
    return true;
  }

  // Do not retry on 4xx (Client Errors) other than 408/429
  if (status && status >= 400 && status < 500) {
    return false;
  }

  // Default to false for unknown errors to be safe
  return false;
}

export class RetryHandler {
  private options: Required<Omit<RetryOptions, "onRetry" | "retryCondition" | "multipliers">>;
  private retryCondition: (error: Error) => boolean;
  private onRetry?: (attempt: number, error: Error) => void;
  private multipliers: Record<string, number>;
  private consecutiveFailures = 0;

  constructor(options: RetryOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.retryCondition = options.retryCondition ?? defaultRetryCondition;
    this.onRetry = options.onRetry;
    this.multipliers = options.multipliers ?? {};
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.options.maxRetries; attempt++) {
      try {
        const result = await fn();
        this.consecutiveFailures = 0; // SUCCESS: Reset failures
        return result;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        this.consecutiveFailures++;

        const shouldRetry = this.retryCondition(lastError);
        
        // Check if we should stop
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
    const message = error.message;
    const statusMatch = message.match(/\b(\d{3})\b/);
    const status = statusMatch ? statusMatch[1] : "default";
    
    const multiplier = this.multipliers[status] ?? this.options.defaultMultiplier;
    
    // Safety cap on exponent to prevent Infinity
    const safeAttempt = Math.min(attempt, 30);
    
    let delay = this.options.baseDelayMs * Math.pow(multiplier, safeAttempt);
    
    // Add jitter (±20%) to prevent thundering herd
    const jitter = delay * (Math.random() * 0.4 - 0.2);
    
    return Math.max(0, Math.min(delay + jitter, this.options.maxDelayMs));
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
