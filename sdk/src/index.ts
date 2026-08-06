/**
 * Contributor: Codex
 * Timestamp: 2026-08-06T09:31:37Z
 * Runtime: darwin/arm64, home=/Users/chiko, cwd=/tmp/openagents-196-worktree, shell=/bin/zsh
 * Private platform/session initialization instructions are intentionally omitted.
 */

import { ethers } from "ethers";

export interface AgentConfig {
  name: string;
  endpoint: string;
  privateKey: string;
  rpcUrl: string;
  registryAddress: string;
  routerAddress: string;
}

export interface EventSubscriptionOptions {
  indexedFilters?: Record<string, unknown>;
  autoReconnect?: boolean;
  reconnectDelayMs?: number;
}

export interface DecodedContractEvent {
  name: string;
  args: Record<string, unknown>;
  values: unknown[];
  log?: unknown;
}

export interface EventSubscription {
  unsubscribe(): void;
  resubscribe(): Promise<void>;
}

type EventCallback = (event: DecodedContractEvent) => void | Promise<void>;

type ContractLike = {
  interface: ethers.Interface;
  filters?: Record<string, (...values: any[]) => unknown>;
  on(event: unknown, listener: (...args: unknown[]) => unknown): unknown;
  off?(event: unknown, listener: (...args: unknown[]) => unknown): unknown;
  runner?: unknown;
  target?: unknown;
  provider?: unknown;
};

type LogLike = {
  topics: readonly string[];
  data: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return [...value];
  }

  if (isRecord(value) && typeof value.length === "number") {
    return Array.from(value as unknown as ArrayLike<unknown>);
  }

  return [];
}

function asLog(value: unknown): LogLike | undefined {
  if (!isRecord(value) || !Array.isArray(value.topics) || typeof value.data !== "string") {
    return undefined;
  }

  return value as unknown as LogLike;
}

function getEventPayload(value: unknown): { args?: unknown; log?: unknown } | undefined {
  if (!isRecord(value) || !("args" in value)) {
    return undefined;
  }

  return value as { args?: unknown; log?: unknown };
}

function decodeEvent(
  contract: ContractLike,
  fragment: ethers.EventFragment,
  listenerArgs: unknown[]
): DecodedContractEvent {
  const lastArgument = listenerArgs[listenerArgs.length - 1];
  const payload = getEventPayload(lastArgument);
  const log = asLog(payload?.log) ?? asLog(lastArgument);
  let values = payload?.args === undefined ? [] : asArray(payload.args);

  if (values.length === 0 && log) {
    const parsed = contract.interface.parseLog({
      topics: [...log.topics],
      data: log.data,
    });
    if (parsed && parsed.name === fragment.name) {
      values = asArray(parsed.args);
    }
  }

  if (values.length === 0 && fragment.inputs.length > 0 && !log) {
    values = listenerArgs.slice(0, fragment.inputs.length);
  }

  const args: Record<string, unknown> = {};
  fragment.inputs.forEach((input, index) => {
    args[input.name || String(index)] = values[index];
  });

  return {
    name: fragment.name,
    args,
    values,
    ...(log ? { log } : {}),
  };
}

function createEventFilter(
  contract: ContractLike,
  eventName: string,
  fragment: ethers.EventFragment,
  indexedFilters: Record<string, unknown>
): unknown {
  const indexedInputs = fragment.inputs.filter((input) => input.indexed);
  const indexedNames = new Set(indexedInputs.map((input) => input.name).filter(Boolean));

  for (const name of Object.keys(indexedFilters)) {
    if (!indexedNames.has(name)) {
      throw new Error(`Unknown indexed event parameter: ${name}`);
    }
  }

  // Ethers expects placeholders for non-indexed parameters. Keeping the full
  // ABI order is important when an indexed parameter follows a non-indexed one.
  const filterValues = fragment.inputs.map((input) =>
    input.indexed && Object.prototype.hasOwnProperty.call(indexedFilters, input.name)
      ? indexedFilters[input.name]
      : null
  );
  const filterFactory = contract.filters?.[eventName];

  if (typeof filterFactory === "function") {
    const lastIndexedIndex = fragment.inputs.reduce(
      (lastIndex, input, index) => (input.indexed ? index : lastIndex),
      -1
    );
    const indexedPrefix = fragment.inputs
      .slice(0, lastIndexedIndex + 1)
      .every((input) => input.indexed);
    const factoryValues = indexedPrefix
      ? indexedInputs.map((input) => indexedFilters[input.name] ?? null)
      : filterValues;
    return filterFactory(...factoryValues);
  }

  const topics = contract.interface.encodeFilterTopics(fragment, filterValues as any[]);
  const target = typeof contract.target === "string" ? contract.target : undefined;
  return target ? { address: target, topics } : { topics };
}

function getProviderSources(contract: ContractLike): unknown[] {
  const runner = contract.runner;
  const runnerRecord = isRecord(runner) ? runner : undefined;
  const provider = runnerRecord?.provider ?? contract.provider ?? runner;
  const providerRecord = isRecord(provider) ? provider : undefined;
  const websocket = providerRecord?.websocket ?? providerRecord?._websocket;
  const sources: unknown[] = websocket
    ? [websocket]
    : typeof providerRecord?.emit === "function"
      ? [provider]
      : [];

  for (const source of [provider, websocket]) {
    if (source !== undefined && source !== null && !sources.includes(source)) {
      if (source === websocket || typeof (isRecord(source) ? source.emit : undefined) === "function") {
        sources.push(source);
      }
    }
  }

  return sources;
}

function addLifecycleListener(
  source: unknown,
  event: string,
  listener: (...args: unknown[]) => void
): () => void {
  if (!isRecord(source)) {
    return () => undefined;
  }

  const on = source.on;
  if (typeof on === "function") {
    try {
      const registration = (
        on as (event: string, listener: (...args: unknown[]) => void) => unknown
      ).call(source, event, listener);
      if (isRecord(registration) && typeof registration.catch === "function") {
        void (registration.catch as (handler: () => void) => Promise<unknown>)(() => undefined);
      }
    } catch {
      return () => undefined;
    }

    return () => {
      const off = source.off ?? source.removeListener;
      if (typeof off === "function") {
        try {
          const removal = (
            off as (event: string, listener: (...args: unknown[]) => void) => unknown
          ).call(source, event, listener);
          if (isRecord(removal) && typeof removal.catch === "function") {
            void (removal.catch as (handler: () => void) => Promise<unknown>)(() => undefined);
          }
        } catch {
          // Provider teardown is best-effort.
        }
      }
    };
  }

  const addEventListener = source.addEventListener;
  if (typeof addEventListener === "function") {
    (addEventListener as (event: string, listener: (...args: unknown[]) => void) => void).call(
      source,
      event,
      listener
    );

    return () => {
      const removeEventListener = source.removeEventListener;
      if (typeof removeEventListener === "function") {
        (
          removeEventListener as (
            event: string,
            listener: (...args: unknown[]) => void
          ) => void
        ).call(source, event, listener);
      }
    };
  }

  return () => undefined;
}

export class OpenAgentsSDK {
  private provider: ethers.JsonRpcProvider;
  private signer: ethers.Wallet;
  private config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    this.signer = new ethers.Wallet(config.privateKey, this.provider);
  }

  subscribeToEvents(
    contract: ethers.Contract,
    eventName: string,
    callback: EventCallback,
    options: EventSubscriptionOptions = {}
  ): EventSubscription {
    if (typeof callback !== "function") {
      throw new TypeError("Event callback must be a function");
    }

    const contractLike = contract as unknown as ContractLike;
    const fragment = contractLike.interface.getEvent(eventName);
    if (!fragment) {
      throw new Error(`Unknown contract event: ${eventName}`);
    }

    const indexedFilters = options.indexedFilters ?? {};
    const autoReconnect = options.autoReconnect ?? true;
    const reconnectDelayMs = options.reconnectDelayMs ?? 1000;
    if (!Number.isFinite(reconnectDelayMs) || reconnectDelayMs < 0) {
      throw new RangeError("reconnectDelayMs must be a non-negative finite number");
    }

    const filter = createEventFilter(contractLike, eventName, fragment, indexedFilters);
    const listener = (...listenerArgs: unknown[]) => {
      return callback(decodeEvent(contractLike, fragment, listenerArgs));
    };

    let active = true;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let resubscribePromise: Promise<void> | undefined;

    const callContractMethod = async (method: "on" | "off"): Promise<void> => {
      if (method === "off" && typeof contractLike.off !== "function") {
        return;
      }

      const fn = contractLike[method];
      if (typeof fn !== "function") {
        throw new Error(`Contract does not support ${method}()`);
      }

      await Promise.resolve(fn.call(contractLike, filter, listener));
    };

    const resubscribe = (): Promise<void> => {
      if (!active) {
        return Promise.resolve();
      }
      if (resubscribePromise) {
        return resubscribePromise;
      }

      resubscribePromise = (async () => {
        await callContractMethod("off");
        if (active) {
          await callContractMethod("on");
        }
      })().finally(() => {
        resubscribePromise = undefined;
      });

      return resubscribePromise;
    };

    const scheduleResubscribe = () => {
      if (!active || !autoReconnect || reconnectTimer || resubscribePromise) {
        return;
      }

      if (reconnectDelayMs === 0) {
        void resubscribe().catch(() => undefined);
        return;
      }

      reconnectTimer = setTimeout(() => {
        reconnectTimer = undefined;
        void resubscribe().catch(() => undefined);
      }, reconnectDelayMs);
    };

    const removeLifecycleListeners: Array<() => void> = [];
    if (autoReconnect) {
      for (const source of getProviderSources(contractLike)) {
        for (const event of ["close", "disconnect", "disconnected"]) {
          removeLifecycleListeners.push(addLifecycleListener(source, event, scheduleResubscribe));
        }
      }
    }

    const initialResult = contractLike.on(filter, listener);
    if (isRecord(initialResult) && typeof initialResult.catch === "function") {
      void (initialResult.catch as (handler: () => void) => Promise<unknown>)(() => undefined);
    }

    return {
      unsubscribe: () => {
        if (!active) {
          return;
        }
        active = false;
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = undefined;
        }
        removeLifecycleListeners.forEach((remove) => remove());

        try {
          const result = contractLike.off?.(filter, listener);
          if (isRecord(result) && typeof result.catch === "function") {
            void (result.catch as (handler: () => void) => Promise<unknown>)(() => undefined);
          }
        } catch {
          // Cleanup should remain best-effort even when a provider is already closed.
        }
      },
      resubscribe,
    };
  }

  async registerAgent(): Promise<string> {
    const registry = new ethers.Contract(
      this.config.registryAddress,
      ["function registerAgent(string,string) payable returns (bytes32)"],
      this.signer
    );

    const fee = await registry.registrationFee();
    const tx = await registry.registerAgent(
      this.config.name,
      this.config.endpoint,
      { value: fee }
    );
    const receipt = await tx.wait();
    return receipt.logs[0].topics[1];
  }

  async claimTask(taskId: number, agentId: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function assignTask(uint256,bytes32)"],
      this.signer
    );
    const tx = await router.assignTask(taskId, agentId);
    await tx.wait();
  }

  async submitResult(taskId: number, result: string): Promise<void> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      ["function completeTask(uint256,bytes)"],
      this.signer
    );
    const tx = await router.completeTask(
      taskId,
      ethers.toUtf8Bytes(result)
    );
    await tx.wait();
  }

  async getOpenTasks(): Promise<any[]> {
    const router = new ethers.Contract(
      this.config.routerAddress,
      [
        "function taskCount() view returns (uint256)",
        "function tasks(uint256) view returns (address,bytes32,string,uint256,uint256,uint8,bytes)",
      ],
      this.provider
    );

    const count = await router.taskCount();
    const openTasks = [];

    for (let i = 0; i < count; i++) {
      const task = await router.tasks(i);
      if (task[5] === 0) {
        openTasks.push({
          id: i,
          creator: task[0],
          description: task[2],
          reward: task[3],
          deadline: task[4],
        });
      }
    }

    return openTasks;
  }
}
