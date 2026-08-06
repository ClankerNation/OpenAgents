/**
 * Contributor: Codex
 * Timestamp: 2026-08-06T09:31:37Z
 * Runtime: darwin/arm64, home=/Users/chiko, cwd=/tmp/openagents-196-worktree, shell=/bin/zsh
 * Private platform/session initialization instructions are intentionally omitted.
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

interface SubscriptionRecord {
  event: string;
  callback: (data: unknown) => void;
  currentId: string | null;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, SubscriptionRecord>();
  private subscriptionAliases = new Map<string, string>();
  private subscriptionId = 0;
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private connectionPromise: Promise<void> | null = null;
  private isConnected = false;
  private shouldReconnect = true;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
  }

  async connect(): Promise<void> {
    if (this.isConnected) {
      return;
    }
    if (this.connectionPromise) {
      return this.connectionPromise;
    }

    this.shouldReconnect = true;
    const connectionPromise = new Promise<void>((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(this.url);
      this.ws = ws;

      ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");

        void this.resubscribeAll()
          .catch((error: unknown) => {
            this.emitProviderError(error);
          })
          .finally(() => {
            if (!settled) {
              settled = true;
              resolve();
            }
          });
      };

      ws.onmessage = (event) => {
        let data: {
          id?: number;
          result?: unknown;
          error?: { message?: string };
          method?: string;
          params?: { subscription?: string; result?: unknown };
        };

        try {
          data = JSON.parse(event.data as string);
        } catch (error) {
          this.emitProviderError(error);
          return;
        }

        if (data.id !== undefined && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          if (data.error) {
            pending.reject(new Error(data.error.message ?? "WebSocket RPC request failed"));
          } else {
            pending.resolve(data.result);
          }
          return;
        }

        if (data.method === "eth_subscription") {
          const serverId = data.params?.subscription;
          const logicalId = serverId ? this.subscriptionAliases.get(serverId) : undefined;
          const subscription = logicalId ? this.subscriptions.get(logicalId) : undefined;
          subscription?.callback(data.params?.result);
        }
      };

      ws.onclose = () => {
        if (this.ws === ws) {
          this.ws = null;
        }
        this.isConnected = false;
        this.rejectPendingRequests(new Error("WebSocket disconnected"));
        this.emit("disconnected");
        if (this.shouldReconnect) {
          this.attemptReconnect();
        }
        if (!settled) {
          settled = true;
          reject(new Error("WebSocket connection closed before it was ready"));
        }
      };

      ws.onerror = (error) => {
        if (!this.isConnected && !settled) {
          settled = true;
          reject(new Error("WebSocket connection failed"));
        }
        this.emitProviderError(error);
      };
    });

    this.connectionPromise = connectionPromise;
    try {
      await connectionPromise;
    } finally {
      if (this.connectionPromise === connectionPromise) {
        this.connectionPromise = null;
      }
    }
  }

  private emitProviderError(error: unknown): void {
    if (this.listenerCount("error") > 0) {
      this.emit("error", error);
    } else {
      this.emit("providerError", error);
    }
  }

  private rejectPendingRequests(error: Error): void {
    for (const pending of this.pendingRequests.values()) {
      pending.reject(error);
    }
    this.pendingRequests.clear();
  }

  private attemptReconnect(): void {
    if (
      !this.shouldReconnect ||
      this.isConnected ||
      this.reconnectTimer ||
      this.reconnectCount >= this.maxReconnectAttempts
    ) {
      if (this.shouldReconnect && this.reconnectCount >= this.maxReconnectAttempts) {
        this.emit("maxReconnectsReached");
      }
      return;
    }

    this.reconnectCount++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  private async resubscribeAll(): Promise<void> {
    for (const [logicalId, subscription] of this.subscriptions) {
      const serverId = (await this.send("eth_subscribe", [subscription.event])) as string;
      subscription.currentId = serverId;
      this.subscriptionAliases.set(serverId, logicalId);
    }
  }

  private resolveSubscription(subscriptionId: string):
    | { logicalId: string; subscription: SubscriptionRecord }
    | undefined {
    const logicalId = this.subscriptions.has(subscriptionId)
      ? subscriptionId
      : this.subscriptionAliases.get(subscriptionId);
    if (!logicalId) {
      return undefined;
    }

    const subscription = this.subscriptions.get(logicalId);
    return subscription ? { logicalId, subscription } : undefined;
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    if (!this.ws || !this.isConnected) {
      throw new Error("WebSocket not connected");
    }

    const id = ++this.requestId;
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      try {
        this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
      } catch (error) {
        this.pendingRequests.delete(id);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const serverId = (await this.send("eth_subscribe", [event])) as string;
    const logicalId = `local-${++this.subscriptionId}`;
    this.subscriptions.set(logicalId, { event, callback, currentId: serverId });
    this.subscriptionAliases.set(serverId, logicalId);
    return serverId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    const resolved = this.resolveSubscription(subscriptionId);
    if (!resolved) {
      return false;
    }

    const { logicalId, subscription } = resolved;
    this.subscriptions.delete(logicalId);
    for (const [alias, aliasLogicalId] of this.subscriptionAliases) {
      if (aliasLogicalId === logicalId) {
        this.subscriptionAliases.delete(alias);
      }
    }

    if (!subscription.currentId || !this.isConnected) {
      return false;
    }

    try {
      return (await this.send("eth_unsubscribe", [subscription.currentId])) as boolean;
    } catch {
      return false;
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
    this.rejectPendingRequests(new Error("WebSocket disconnected"));
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
  }
}
