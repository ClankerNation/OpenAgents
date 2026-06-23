import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  listenerWarningThreshold?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

const DEFAULT_LISTENER_WARNING_THRESHOLD = 10;

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private listenerWarningThreshold: number;
  private reconnectCount = 0;
  private isConnected = false;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.listenerWarningThreshold = config.listenerWarningThreshold ?? DEFAULT_LISTENER_WARNING_THRESHOLD;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);
        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          if (data.error) {
            pending.reject(new Error(data.error.message || data.error));
          } else {
            pending.resolve(data.result);
          }
        } else if (data.method && this.subscriptions.has(data.method)) {
          this.subscriptions.get(data.method)!(data.params);
        }
      };

      this.ws.onerror = (error) => {
        reject(error);
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.emit("disconnected");
        this.handleReconnect();
      };
    });
  }

  private handleReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectAttempts", this.maxReconnectAttempts);
      return;
    }

    this.reconnectCount++;
    setTimeout(() => {
      this.reconnect();
    }, this.reconnectInterval * this.reconnectCount);
  }

  private reconnect(): void {
    // Remove all listeners before reconnecting to prevent duplicates
    if (this.ws) {
      this.ws.removeAllListeners();
    }

    // Check listener count before reconnect
    const listenerCount = this.listenerCount ? this.listenerCount() : 0;
    if (listenerCount > this.listenerWarningThreshold) {
      console.warn(
        `WebSocketProvider: high listener count (${listenerCount}) before reconnect. Consider cleaning up subscriptions.`
      );
    }

    const connectPromise = new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.emit("reconnected");
        // Re-subscribe to existing subscriptions
        for (const [method, handler] of this.subscriptions) {
          this.send({
            method: "subscribe",
            params: { topic: method },
          });
        }
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);
        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          if (data.error) {
            pending.reject(new Error(data.error.message || data.error));
          } else {
            pending.resolve(data.result);
          }
        } else if (data.method && this.subscriptions.has(data.method)) {
          this.subscriptions.get(data.method)!(data.params);
        }
      };

      this.ws.onerror = (error) => {
        reject(error);
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.handleReconnect();
      };
    });

    connectPromise.catch(() => {
      // Reconnect attempt failed, handleReconnect will try again
    });
  }

  send(request: Record<string, unknown>): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.isConnected || !this.ws) {
        reject(new Error("WebSocket is not connected"));
        return;
      }

      const id = ++this.requestId;
      this.pendingRequests.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ ...request, id }));
    });
  }

  subscribe(topic: string, handler: (data: unknown) => void): void {
    this.subscriptions.set(topic, handler);
    if (this.isConnected) {
      this.send({
        method: "subscribe",
        params: { topic },
      });
    }
  }

  unsubscribe(topic: string): void {
    this.subscriptions.delete(topic);
    if (this.isConnected) {
      this.send({
        method: "unsubscribe",
        params: { topic },
      });
    }
  }

  disconnect(): void {
    this.reconnectCount = this.maxReconnectAttempts; // Stop reconnect attempts
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
    }
    this.isConnected = false;
    this.emit("disconnected");
  }
}
