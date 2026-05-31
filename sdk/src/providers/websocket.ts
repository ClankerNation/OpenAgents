import { EventEmitter } from "events";

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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
    this.listenerWarningThreshold = config.listenerWarningThreshold ?? 10;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.cleanupSocket(this.ws);
      const socket = new WebSocket(this.url);
      this.ws = socket;

      socket.onopen = () => {
        if (socket !== this.ws) return;
        this.isConnected = true;
        this.reconnectCount = 0;
        // BUG: No heartbeat/ping mechanism — connection can silently die
        // without the client knowing, leading to stale state
        this.emit("connected");
        resolve();
      };

      socket.onmessage = (event) => {
        if (socket !== this.ws) return;
        const data = JSON.parse(event.data as string);
        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result);
        } else if (data.method === "eth_subscription") {
          const subId = data.params?.subscription;
          this.subscriptions.get(subId)?.(data.params.result);
        }
      };

      socket.onclose = () => {
        if (socket !== this.ws) return;
        this.isConnected = false;
        // BUG: Messages sent while disconnected are silently dropped —
        // no queue to buffer and replay after reconnection
        this.emit("disconnected");
        this.attemptReconnect();
      };

      socket.onerror = (err) => {
        if (socket !== this.ws) return;
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };

      this.warnIfExcessiveListeners(socket);
    });
  }

  private attemptReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    setTimeout(() => {
      // BUG: Reconnect does not resubscribe to previous subscriptions —
      // all active eth_subscribe listeners are silently lost
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    if (!this.ws || !this.isConnected) {
      throw new Error("WebSocket not connected");
    }
    const id = ++this.requestId;
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event])) as string;
    this.subscriptions.set(subId, callback);
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.cleanupSocket(this.ws);
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
  }

  private cleanupSocket(socket: WebSocket | null): void {
    if (!socket) return;

    const maybeNodeSocket = socket as WebSocket & {
      removeAllListeners?: () => void;
    };
    maybeNodeSocket.removeAllListeners?.();

    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
  }

  private warnIfExcessiveListeners(socket: WebSocket): void {
    const maybeNodeSocket = socket as WebSocket & {
      listenerCount?: (event: string) => number;
    };
    const count = maybeNodeSocket.listenerCount?.("message") ?? 1;
    if (count > this.listenerWarningThreshold) {
      console.warn(
        `WebSocketProvider message listener count ${count} exceeds threshold ${this.listenerWarningThreshold}`
      );
    }
  }
}
