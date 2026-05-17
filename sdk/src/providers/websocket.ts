/**
 * @contributor
 * name: opencode-gaotax2006
 * platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
 * timestamp: 2026-05-17T14:30:00Z
 */

import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  heartbeatIntervalMs?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface QueuedMessage {
  method: string;
  params: unknown[];
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
  private reconnectCount = 0;
  private isConnected = false;
  private messageQueue: QueuedMessage[] = [];
  private heartbeatInterval: number;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatExpectingPong = false;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.heartbeatInterval = config.heartbeatIntervalMs ?? 30_000;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.startHeartbeat();
        this.flushMessageQueue();
        this.resubscribe();
        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);

        if (data.method === "pong") {
          this.heartbeatExpectingPong = false;
          return;
        }

        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result);
        } else if (data.method === "eth_subscription") {
          const subId = data.params?.subscription;
          this.subscriptions.get(subId)?.(data.params.result);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.stopHeartbeat();
        this.emit("disconnected");
        this.attemptReconnect();
      };

      this.ws.onerror = (err) => {
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };
    });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (!this.ws || !this.isConnected) return;

      if (this.heartbeatExpectingPong) {
        this.ws.close();
        return;
      }

      this.heartbeatExpectingPong = true;
      try {
        this.ws.send(JSON.stringify({ jsonrpc: "2.0", method: "ping", id: 0 }));
      } catch {
        this.ws.close();
      }
    }, this.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    this.heartbeatExpectingPong = false;
  }

  private flushMessageQueue(): void {
    const queue = this.messageQueue;
    this.messageQueue = [];
    for (const msg of queue) {
      this.send(msg.method, msg.params).then(msg.resolve).catch(msg.reject);
    }
  }

  private resubscribe(): void {
    if (this.subscriptions.size === 0) return;
    const entries = [...this.subscriptions.entries()];
    this.subscriptions.clear();
    for (const [, callback] of entries) {
      this.send("eth_subscribe", ["newHeads"]).then((subId) => {
        this.subscriptions.set(subId as string, callback);
      }).catch(() => {});
    }
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

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    if (!this.ws || !this.isConnected) {
      return new Promise((resolve, reject) => {
        this.messageQueue.push({ method, params, resolve, reject });
      });
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
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
  }
}
