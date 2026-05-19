import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  pingIntervalMs?: number;
  pingTimeoutMs?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface ActiveSubscription {
  event: string;
  callback: (data: unknown) => void;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private pendingRequests = new Map<number, PendingRequest>();
  private requestId = 0;
  private subscriptions = new Map<string, (data: unknown) => void>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;

  // Queue to buffer pending outgoing messages while disconnected (max 100)
  private queue: string[] = [];
  private readonly maxQueueSize = 100;

  // Active subscription mapping (event -> callback) to resubscribe upon reconnect
  private activeSubscriptions = new Map<string, ActiveSubscription>();

  // Heartbeat ping/pong settings
  private pingIntervalMs: number;
  private pingTimeoutMs: number;
  private pingTimer: any = null;
  private pingTimeoutTimer: any = null;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.pingIntervalMs = config.pingIntervalMs ?? 10000;
    this.pingTimeoutMs = config.pingTimeoutMs ?? 5000;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = async () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        
        // Start heartbeat ping/pong protocol
        this.startHeartbeat();

        // Flush any queued messages
        this.flushQueue();

        // Auto-resubscribe active subscriptions
        await this.resubscribeAll();

        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        // Reset heartbeat timeout when we receive a message
        this.resetHeartbeatTimeout();

        const data = JSON.parse(event.data as string);

        // Filter out heartbeat pong messages if any
        if (data.method === "pong") {
          return;
        }

        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          pending.resolve(data.result);
        } else if (data.method && data.params) {
          const subscriptionId = data.params.subscription;
          const callback = this.subscriptions.get(subscriptionId);
          if (callback) {
            callback(data.params.result);
          }
        }
      };

      this.ws.onclose = () => {
        this.handleDisconnect();
      };

      this.ws.onerror = (err) => {
        this.emit("error", err);
        reject(err);
      };
    });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.pingTimer = setInterval(() => {
      if (this.ws && this.isConnected) {
        // Send ping frame or JSON-RPC ping
        try {
          this.ws.send(JSON.stringify({ jsonrpc: "2.0", method: "ping" }));
          
          // Set a timeout to detect connection loss
          this.pingTimeoutTimer = setTimeout(() => {
            this.emit("heartbeat_timeout");
            this.handleDisconnect();
          }, this.pingTimeoutMs);
        } catch (e) {
          this.handleDisconnect();
        }
      }
    }, this.pingIntervalMs);
  }

  private resetHeartbeatTimeout(): void {
    if (this.pingTimeoutTimer) {
      clearTimeout(this.pingTimeoutTimer);
      this.pingTimeoutTimer = null;
    }
  }

  private stopHeartbeat(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    this.resetHeartbeatTimeout();
  }

  private handleDisconnect(): void {
    const wasConnected = this.isConnected;
    this.isConnected = false;
    this.stopHeartbeat();

    if (wasConnected) {
      this.emit("disconnected");
    }

    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {}
      this.ws = null;
    }

    this.attemptReconnect();
  }

  private attemptReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    setTimeout(() => {
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  private flushQueue(): void {
    while (this.queue.length > 0 && this.ws && this.isConnected) {
      const msg = this.queue.shift();
      if (msg) {
        try {
          this.ws.send(msg);
        } catch (e) {
          // Re-insert at front of queue if send failed
          this.queue.unshift(msg);
          break;
        }
      }
    }
  }

  private async resubscribeAll(): Promise<void> {
    const subsToRestore = Array.from(this.activeSubscriptions.entries());
    // Clear subscriptions map to avoid duplicate mappings with old subIds
    this.subscriptions.clear();

    for (const [oldSubId, sub] of subsToRestore) {
      try {
        const newSubId = (await this.send("eth_subscribe", [sub.event])) as string;
        this.subscriptions.set(newSubId, sub.callback);
        
        // Update active subscription reference with the new subscription ID
        this.activeSubscriptions.delete(oldSubId);
        this.activeSubscriptions.set(newSubId, sub);
      } catch (e) {
        this.emit("error", new Error(`Failed to resubscribe to event ${sub.event}: ${(e as Error).message}`));
      }
    }
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    const id = ++this.requestId;
    const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });

    if (!this.ws || !this.isConnected) {
      if (this.queue.length >= this.maxQueueSize) {
        this.queue.shift(); // Drop oldest message to respect bounds
      }
      this.queue.push(msg);
      
      // Return a promise that resolves when reconnect happens or rejects on failure/timeout
      return new Promise((resolve, reject) => {
        this.pendingRequests.set(id, { resolve, reject });
      });
    }

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      try {
        this.ws!.send(msg);
      } catch (err) {
        this.pendingRequests.delete(id);
        reject(err);
      }
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event])) as string;
    this.subscriptions.set(subId, callback);
    this.activeSubscriptions.set(subId, { event, callback });
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    this.activeSubscriptions.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.queue = [];
    this.activeSubscriptions.clear();
    this.subscriptions.clear();
  }
}
