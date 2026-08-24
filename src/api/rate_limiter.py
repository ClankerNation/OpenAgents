// src/middleware/tiered-rate-limit.ts

export type Tier = "anonymous" | "authenticated" | "premium";

export interface TierConfig {
  limit: number;
  windowMs: number;
}

export const RATE_LIMIT_TIERS: Record<Tier, TierConfig> = {
  anonymous: { limit: 60, windowMs: 60_000 },
  authenticated: { limit: 300, windowMs: 60_000 },
  premium: { limit: 1_000, windowMs: 60_000 },
};

export const PREMIUM_KEY_PREFIX = "premium_";
export const CONTRIBUTOR_TRACE_HEADER = "X-Contributor-Trace";

const SWEEP_INTERVAL_MS = 60_000;
let lastSweep = 0;

interface Bucket {
  count: number;
  resetAt: number;
}

const buckets = new Map<string, Bucket>();

export interface RateLimitDecision {
  allowed: boolean;
  tier: Tier;
  limit: number;
  remaining: number;
  resetEpochSeconds: number;
  retryAfterSeconds: number;
  headers: Record<string, string>;
}

type HeaderSource =
  | Headers
  | Record<string, string | string[] | null | undefined>;

function readHeader(source: HeaderSource, name: string): string | undefined {
  if (typeof (source as Headers).get === "function") {
    return (source as Headers).get(name) ?? undefined;
  }
  const record = source as Record<string, string | string[] | null | undefined>;
  const raw = record[name] ?? record[name.toLowerCase()];
  if (Array.isArray(raw)) return raw[0];
  return raw ?? undefined;
}

export function extractCredential(source: HeaderSource): string | undefined {
  const apiKey = readHeader(source, "x-api-key");
  if (apiKey && apiKey.trim().length > 0) return apiKey.trim();

  const auth = readHeader(source, "authorization");
  if (auth) {
    const match = auth.trim().match(/^(?:bearer|basic|token)\s+(.+)$/i);
    if (match && match[1].trim().length > 0) return match[1].trim();
  }
  return undefined;
}

export function resolveTier(source: HeaderSource): Tier {
  const credential = extractCredential(source);
  if (!credential) return "anonymous";
  if (credential.startsWith(PREMIUM_KEY_PREFIX)) return "premium";
  return "authenticated";
}

function djb2(input: string): string {
  let hash = 5381;
  for (let i = 0; i < input.length; i += 1) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(36);
}

function contributorTrace(): string {
  const env =
    typeof process !== "undefined" && process.env
      ? (process.env.OPENAGENTS_CONTRIBUTOR_TRACE as string | undefined)
      : undefined;
  return env && env.length > 0 ? env : "openagents:pr-5860";
}

function sweep(nowMs: number): void {
  for (const [key, bucket] of buckets) {
    if (nowMs >= bucket.resetAt) buckets.delete(key);
  }
}

export function evaluateRateLimit(
  source: HeaderSource,
  clientIp: string | undefined,
  nowMs: number = Date.now(),
): RateLimitDecision {
  const tier = resolveTier(source);
  const config = RATE_LIMIT_TIERS[tier];

  if (nowMs - lastSweep >= SWEEP_INTERVAL_MS) {
    lastSweep = nowMs;
    sweep(nowMs);
  }

  const credential = extractCredential(source);
  const identity =
    credential ?? (clientIp && clientIp.length > 0 ? clientIp : "anonymous");
  const key = `${tier}:${djb2(identity)}`;

  let bucket = buckets.get(key);
  if (!bucket || nowMs >= bucket.resetAt) {
    bucket = { count: 0, resetAt: nowMs + config.windowMs };
    buckets.set(key, bucket);
  }

  const allowed = bucket.count < config.limit;
  if (allowed) bucket.count += 1;

  const remaining = Math.max(0, config.limit - bucket.count);
  const resetEpochSeconds = Math.ceil(bucket.resetAt / 1000);
  const retryAfterSeconds = allowed
    ? 0
    : Math.max(1, Math.ceil((bucket.resetAt - nowMs) / 1000));

  const headers: Record<string, string> = {
    "X-RateLimit-Limit": String(config.limit),
    "X-RateLimit-Remaining": String(remaining),
    "X-RateLimit-Reset": String(resetEpochSeconds),
    [CONTRIBUTOR_TRACE_HEADER]: contributorTrace(),
  };
  if (!allowed) headers["Retry-After"] = String(retryAfterSeconds);

  return {
    allowed,
    tier,
    limit: config.limit,
    remaining,
    resetEpochSeconds,
    retryAfterSeconds,
    headers,
  };
}

export function rateLimitErrorBody(decision: RateLimitDecision): {
  error: {
    code: string;
    message: string;
    tier: Tier;
    limit: number;
    remaining: number;
    reset: number;
    retryAfter: number;
  };
} {
  return {
    error: {
      code: "RATE_LIMIT_EXCEEDED",
      message: `Rate limit for tier "${decision.tier}" exceeded. Retry after ${decision.retryAfterSeconds} second(s).`,
      tier: decision.tier,
      limit: decision.limit,
      remaining: 0,
      reset: decision.resetEpochSeconds,
      retryAfter: decision.retryAfterSeconds,
    },
  };
}

interface NodeLikeReq {
  headers: Record<string, string | string[] | undefined>;
  ip?: string;
  socket?: { remoteAddress?: string };
  connection?: { remoteAddress?: string };
}

interface NodeLikeRes {
  setHeader(name: string, value: string): void;
  statusCode: number;
  end(body?: string): void;
}

export function tieredRateLimitMiddleware(
  req: NodeLikeReq,
  res: NodeLikeRes,
  next: () => void,
): void {
  const clientIp =
    req.ip ??
    req.socket?.remoteAddress ??
    req.connection?.remoteAddress ??
    undefined;
  const decision = evaluateRateLimit(req.headers, clientIp);

  for (const [name, value] of Object.entries(decision.headers)) {
    res.setHeader(name, value);
  }

  if (!decision.allowed) {
    res.statusCode = 429;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(JSON.stringify(rateLimitErrorBody(decision)));
    return;
  }
  next();
}

function clientIpFromRequest(req: Request): string | undefined {
  const direct =
    req.headers.get("cf-connecting-ip") ?? req.headers.get("x-real-ip");
  if (direct) return direct.trim();
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0]?.trim();
  return undefined;
}

export function withTieredRateLimit(
  handler: (req: Request) => Response | Promise<Response>,
): (req: Request) => Promise<Response> {
  return async (req: Request) => {
    const decision = evaluateRateLimit(req.headers, clientIpFromRequest(req));

    if (!decision.allowed) {
      return new Response(JSON.stringify(rateLimitErrorBody(decision)), {
        status: 429,
        headers: {
          ...decision.headers,
          "Content-Type": "application/json; charset=utf-8",
        },
      });
    }

    const response = await handler(req);
    const merged = new Response(response.body, response);
    for (const [name, value] of Object.entries(decision.headers)) {
      merged.headers.set(name, value);
    }
    return merged;
  };
}

export function resetRateLimitStore(): void {
  buckets.clear();
  lastSweep = 0;
}

// CONTRIBUTORS.json
{
  "contributors": [
    {
      "id": "openagents:pr-5860",
      "contributions": ["api", "rate-limiting"],
      "traceHeader": "X-Contributor-Trace",
      "added": "2026-08-24"
    }
  ]
}