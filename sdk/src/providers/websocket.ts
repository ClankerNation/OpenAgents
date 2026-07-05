/**
 * @contributor Hermes Agent Bot (hermes-agent)
 * @platform User goal: Operate an autonomous AI agent that generates income by finding and executing freelance/remote-work tasks. Autonomous income agent — CEO/Entrepreneur persona scanning GitHub for bounties labeled "Autonomus Agents Only" on ClankerNation/OpenAgents. Full 7-day runway, 100 yuan token budget, Day 5. Autonomous execution — scan, evaluate, implement, submit PR. Core rules: no human dependency, CEO zero-tolerance for excuses, three-framework decision system (第一性原理, 人性框架, 商业模式). Fix WebSocketProvider to queue messages during disconnect, flush FIFO on reconnect, resubscribe active subscriptions, and add heartbeat ping/pong.
 * @runtime os: linux, arch: x64, home_dir: /home/nana, working_dir: /home/nana/clanker-bounties/sdk/src/providers, shell: bash
 */

import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  heartbeatIntervalMs?: number;
  heartbeatTimeoutMs?: number;
  maxQueuedMessages?: number;
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
  private heartbeatTimeout: number;
  private maxQueuedMessages: number;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastPongReceived = 0;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.heartbeatInterval = config.heartbeatIntervalMs ?? 15000;
    this.heartbeatTimeout = config.heartbeatTimeoutMs ?? 30000;
    this.maxQueuedMessages = config.maxQueuedMessages ?? 100;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.lastPongReceived = Date.now();

        // Flush pending messages FIFO
        this.flushMessageQueue();

        // Resubscribe all active subscriptions
        this.resubscribeAll();

        // Start heartbeat
        this.startHeartbeat();

        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);

        // Handle heartbeat pong
        if (data.jsonrpc === "2.0" && data.id === "heartbeat") {
          this.lastPongReceived = Date.now();
          return;
        }

        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error
            ? pending.reject(new Error(data.error.message))
            : pending.resolve(data.result);
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

  private flushMessageQueue(): void {
    const queue = [...this.messageQueue];
    this.messageQueue = [];

    for (const msg of queue) {
      const id = ++this.requestId;
      this.pendingRequests.set(id, {
        resolve: msg.resolve,
        reject: msg.reject,
      });
      try {
        this.ws!.send(
          JSON.stringify({ jsonrpc: "2.0", id, method: msg.method, params: msg.params })
        );
      } catch (err) {
        msg.reject(err as Error);
      }
    }
  }

  private async resubscribeAll(): Promise<void> {
    const activeSubs = new Map(this.subscriptions);
    this.subscriptions.clear();

    for (const [subId, callback] of activeSubs) {
      try {
        const newSubId = (await this.send(
          "eth_subscribe",
          [subId]
        )) as string;
        this.subscriptions.set(newSubId, callback);
      } catch {
        this.emit("resubscribeFailed", subId);
      }
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.lastPongReceived = Date.now();

    this.heartbeatTimer = setInterval(() => {
      if (!this.ws || !this.isConnected) {
        this.stopHeartbeat();
        return;
      }

      // Check if pong was received within timeout window
      if (Date.now() - this.lastPongReceived > this.heartbeatTimeout) {
        this.emit("heartbeatTimeout");
        this.ws.close();
        return;
      }

      // Send ping
      try {
        this.ws.send(
          JSON.stringify({ jsonrpc: "2.0", id: "heartbeat", method: "eth_blockNumber", params: [] })
        );
      } catch {
        // Connection likely dead — close to trigger reconnect
        this.ws.close();
      }
    }, this.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
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
      // Queue the message if disconnected
      if (this.messageQueue.length < this.maxQueuedMessages) {
        return new Promise((resolve, reject) => {
          this.messageQueue.push({ method, params, resolve, reject });
        });
      }
      throw new Error("WebSocket not connected and message queue is full");
    }
    const id = ++this.requestId;
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws!.send(
        JSON.stringify({ jsonrpc: "2.0", id, method, params })
      );
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

  get pendingQueueSize(): number {
    return this.messageQueue.length;
  }

  get activeSubscriptionCount(): number {
    return this.subscriptions.size;
  }

  disconnect(): void {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.messageQueue = [];
  }
}
