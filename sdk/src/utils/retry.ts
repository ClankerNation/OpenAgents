// Conditional retry with exponential backoff
export class RetryManager {
  private maxAttempts: number;
  private baseDelay: number;
  
  constructor(maxAttempts = 3, baseDelay = 1000) {
    this.maxAttempts = maxAttempts;
    this.baseDelay = baseDelay;
  }
  
  async retry<T>(fn: () => Promise<T>, shouldRetry?: (error: any) => boolean): Promise<T> {
    let lastError: any;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error;
        // Fix #137: conditional retry — only retry if shouldRetry returns true
        if (shouldRetry && !shouldRetry(error)) throw error;
        if (attempt === this.maxAttempts) throw error;
        const delay = this.baseDelay * Math.pow(2, attempt - 1);
        await new Promise(r => setTimeout(r, delay));
      }
    }
    throw lastError;
  }
}
