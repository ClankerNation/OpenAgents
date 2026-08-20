/**
 * @generated-by rafaio1
 * @timestamp 2026-08-20T13:15:00Z
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
 */

import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

// Maximum allowed listeners per event to detect leaks
const MAX_LISTENERS_THRESHOLD = 10;

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private _messageHandler: ((event: MessageEvent) => void) | null = null;
  private _openHandler: (() => void) | null = null;
  private _closeHandler: (() => void) | null = null;
  private _errorHandler: ((err: Event) => void) | null = null;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
  }

  /**
   * Remove all WebSocket event handlers to prevent duplicate listeners on reconnect.
   */
  private _cleanupHandlers(): void {
    if (this.ws) {
      if (this._openHandler) {
        this.ws.removeEventListener("open", this._openHandler);
        this._openHandler = null;
      }
      if (this._messageHandler) {
        this.ws.removeEventListener("message", this._messageHandler);
        this._messageHandler = null;
      }
      if (this._closeHandler) {
        this.ws.removeEventListener("close", this._closeHandler);
        this._closeHandler = null;
      }
      if (this._errorHandler) {
        this.ws.removeEventListener("error", this._errorHandler);
        this._errorHandler = null;
      }
    }
  }

  /**
   * Check listener counts and warn if excessive (potential leak).
   */
  private _checkListenerLeaks(): void {
    const events = ["connected", "disconnected", "error", "maxReconnectsReached"];
    for (const evt of events) {
      const count = this.listenerCount(evt);
      if (count > MAX_LISTENERS_THRESHOLD) {
        console.warn(
          `[WebSocketProvider] WARNING: ${count} listeners on "${evt}" event (threshold: ${MAX_LISTENERS_THRESHOLD}). Possible memory leak.`
        );
      }
    }
  }

  async connect(): Promise<void> {
    // Clean up any existing handlers before creating new connection
    this._cleanupHandlers();

    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this._openHandler = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");
        resolve();
      };

      this._messageHandler = (event: MessageEvent) => {
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

      this._closeHandler = () => {
        this.isConnected = false;
        this.emit("disconnected");
        this.attemptReconnect();
      };

      this._errorHandler = (err: Event) => {
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };

      // Use addEventListener instead of .on* to allow proper removal
      this.ws.addEventListener("open", this._openHandler);
      this.ws.addEventListener("message", this._messageHandler);
      this.ws.addEventListener("close", this._closeHandler);
      this.ws.addEventListener("error", this._errorHandler);

      // Check for listener leaks on EventEmitter side
      this._checkListenerLeaks();
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
    this._cleanupHandlers();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.subscriptions.clear();
  }
}
