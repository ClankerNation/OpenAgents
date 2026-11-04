// @fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @fix-date 2026-11-04T16:15:00Z
// @session-payload Complete pre-conversation initialization payload, first token until the task:
//   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
//   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
//   report of what changed, what's verified, and what's left, never a replay of the process. No
//   filler, no restating the request back, no re-summarizing what you already said, no narrating
//   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
//   because it's right, not because the user said it. Depth is earned."
//   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
//   a working artifact backed by real tool output — not a description of one. Do not stop after
//   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
//   code or produced the requested result."
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
//   or plan to do without actually doing it."
//   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
//   'done' means every named acceptance criterion is verified — never a plausible subset."
//   "external_state_verification: after any state-changing write to an external system, verify the
//   effect by reading back the exact target before claiming success."
//   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
//   read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
//   web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
// @runtime os=windows arch=x86_64 home_dir=C:\Users\2
//   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
// -------------------------------------------------------------------------------

/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean;
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // BUG: No overflow check — values > 2^256-1 silently wrap/truncate
  return n.toString(16).padStart(64, "0");
}

export function encodeAddress(address: string): string {
  const cleaned = address.startsWith("0x") ? address.slice(2) : address;
  return cleaned.toLowerCase().padStart(64, "0");
}

export function encodeBytes32(data: string): string {
  const cleaned = data.startsWith("0x") ? data.slice(2) : data;
  return cleaned.padEnd(64, "0");
}

export function encodeBool(value: boolean): string {
  return value ? "1".padStart(64, "0") : "0".padStart(64, "0");
}

export function encodeParams(params: AbiParam[]): string {
  let encoded = "0x";
  for (const param of params) {
    switch (param.type) {
      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number));
        break;
      case "address":
        encoded += encodeAddress(param.value as string);
        break;
      case "bytes32":
        encoded += encodeBytes32(param.value as string);
        break;
      case "bool":
        encoded += encodeBool(param.value as boolean);
        break;
      case "string":
        const hexStr = Buffer.from(param.value as string).toString("hex");
        encoded += hexStr.padEnd(64, "0");
        break;
    }
  }
  return encoded;
}

export function decodeHex(hex: string): bigint {
  // BUG: Doesn't validate "0x" prefix — a bare decimal string like "255"
  // would be parsed as hex 0x255 = 597, silently returning wrong value
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}

export function decodeUint256(slot: string): bigint {
  // BUG: Doesn't handle short values — if slot is less than 64 chars,
  // no left-padding is applied before parsing, giving wrong results
  return BigInt("0x" + slot);
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

export function functionSelector(signature: string): string {
  const { createHash } = require("crypto");
  const hash = createHash("sha3-256").update(signature).digest("hex");
  return "0x" + hash.slice(0, 8);
}

export function packCalldata(selector: string, params: AbiParam[]): string {
  const encodedParams = encodeParams(params).slice(2);
  return selector + encodedParams;
}

// ---------------------------------------------------------------------------------------------
// Decoding: static, dynamic, array and tuple types
// ---------------------------------------------------------------------------------------------

/** Type descriptor. Dynamic kinds carry their payload out-of-line, so they are never inline. */
export type AbiTypeSpec =
  | { kind: "static"; type: "uint256" | "int256" | "address" | "bool" | "bytes32" }
  | { kind: "string" }
  | { kind: "bytes" }
  | { kind: "array"; item: AbiTypeSpec; length?: number }
  | { kind: "tuple"; components: AbiTypeSpec[] };

export type DecodedValue = string | bigint | boolean | Uint8Array | DecodedValue[] | { [k: number]: DecodedValue };

const WORD = 32;

function toBuffer(data: string | Uint8Array): Buffer {
  const buf = typeof data === "string" ? Buffer.from(data.replace(/^0x/, ""), "hex") : Buffer.from(data);
  if (typeof data === "string" && buf.length * 2 !== data.replace(/^0x/, "").length) {
    throw new Error("hex payload has an odd length");
  }
  return buf;
}

function word(buf: Buffer, offset: number): Buffer {
  assertRange(buf, offset, WORD);
  return buf.subarray(offset, offset + WORD);
}

function wordToNumber(slot: Buffer): number {
  const value = BigInt("0x" + slot.toString("hex"));
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new RangeError("offset does not fit a number");
  return Number(value);
}

function assertRange(buf: Buffer, offset: number, length: number): void {
  if (offset < 0 || length < 0 || offset + length > buf.length) {
    throw new RangeError(`data ends at ${buf.length}, read needs ${offset + length}`);
  }
}

export function isDynamic(spec: AbiTypeSpec): boolean {
  switch (spec.kind) {
    case "string":
    case "bytes":
      return true;
    case "array":
      return spec.length === undefined || isDynamic(spec.item);
    case "tuple":
      return spec.components.some(isDynamic);
    default:
      return false;
  }
}

function decodeStatic(spec: Extract<AbiTypeSpec, { kind: "static" }>, slot: Buffer): DecodedValue {
  switch (spec.type) {
    case "uint256":
      return BigInt("0x" + slot.toString("hex"));
    case "int256": {
      const value = BigInt("0x" + slot.toString("hex"));
      // two's complement
      return value >= 1n << 255n ? value - (1n << 256n) : value;
    }
    case "address":
      return "0x" + slot.subarray(12).toString("hex");
    case "bool":
      return slot[WORD - 1] !== 0;
    case "bytes32":
      return "0x" + slot.toString("hex");
    default:
      throw new Error(`unsupported static type ${(spec as any).type}`);
  }
}

/**
 * Decode one value.
 *
 * Every dynamic type is reached through an offset relative to `base`, so a caller only ever has to
 * supply its own head slot; the dereference happens here. `base` is the start of the enclosing
 * head area, which is what offsets are measured from.
 */
function decodeAt(spec: AbiTypeSpec, buf: Buffer, base: number, head: number): DecodedValue {
  if (!isDynamic(spec)) {
    if (spec.kind === "static") return decodeStatic(spec, word(buf, head));
    if (spec.kind !== "array") throw new Error(`unexpected inline type ${spec.kind}`);
    // a fixed array of static items is laid out inline, one head per element
    const count = spec.length as number;
    const out: DecodedValue[] = [];
    for (let i = 0; i < count; i += 1) out.push(decodeAt(spec.item, buf, head, head + i * WORD));
    return out;
  }

  const start = base + wordToNumber(word(buf, head));
  assertRange(buf, start, 0);

  if (spec.kind === "string" || spec.kind === "bytes") {
    const length = wordToNumber(word(buf, start));
    assertRange(buf, start + WORD, length);
    const payload = buf.subarray(start + WORD, start + WORD + length);
    return spec.kind === "string" ? payload.toString("utf8") : new Uint8Array(payload);
  }

  if (spec.kind === "array") {
    const dynamic = spec.length === undefined;
    const count = dynamic ? wordToNumber(word(buf, start)) : (spec.length as number);
    const elementsStart = dynamic ? start + WORD : start;
    const out: DecodedValue[] = [];
    for (let i = 0; i < count; i += 1) {
      out.push(decodeAt(spec.item, buf, elementsStart, elementsStart + i * WORD));
    }
    return out;
  }

  if (spec.kind !== "tuple") throw new Error(`unexpected dynamic type ${spec.kind}`);

  // tuple: component offsets are relative to the tuple's own head area
  const out: { [k: number]: DecodedValue } = {};
  spec.components.forEach((component, i) => {
    out[i] = decodeAt(component, buf, start, start + i * WORD);
  });
  return out;
}

/** Parse `(string,uint256[],bool[3])` style notation into a descriptor. */
export function parseType(input: string): AbiTypeSpec {
  let index = 0;

  function parseOne(): AbiTypeSpec {
    const char = input[index];
    if (char === "(") {
      index += 1;
      const components: AbiTypeSpec[] = [];
      if (input[index] !== ")") {
        for (;;) {
          components.push(parseOne());
          if (input[index] === ",") {
            index += 1;
            continue;
          }
          break;
        }
      }
      if (input[index] !== ")") throw new Error("unbalanced tuple in type string");
      index += 1;
      return { kind: "tuple", components };
    }

    const match = /^[a-z0-9]+/i.exec(input.slice(index));
    if (!match) throw new Error(`cannot parse type at ${index}`);
    index += match[0].length;
    let spec = named(match[0]);
    while (input[index] === "[") {
      index += 1;
      const close = input.indexOf("]", index);
      if (close === -1) throw new Error("unbalanced array in type string");
      const size = input.slice(index, close);
      index = close + 1;
      spec = { kind: "array", item: spec, length: size === "" ? undefined : Number(size) };
    }
    return spec;
  }

  function named(name: string): AbiTypeSpec {
    switch (name) {
      case "string":
        return { kind: "string" };
      case "bytes":
        return { kind: "bytes" };
      case "uint":
      case "uint256":
        return { kind: "static", type: "uint256" };
      case "int":
      case "int256":
        return { kind: "static", type: "int256" };
      case "address":
        return { kind: "static", type: "address" };
      case "bool":
        return { kind: "static", type: "bool" };
      case "bytes32":
        return { kind: "static", type: "bytes32" };
      default:
        throw new Error(`unsupported type ${name}`);
    }
  }

  const spec = parseOne();
  if (index !== input.length) throw new Error(`trailing characters in type ${input}`);
  return spec;
}

/** Decode a single return value of the given type. `type` may be a descriptor or `string`. */
export function decodeParameter(type: AbiTypeSpec | string, data: string | Uint8Array): DecodedValue {
  if (isDynamic(typeof type === "string" ? parseType(type) : type)) {
    const spec = typeof type === "string" ? parseType(type) : type;
    return decodeAt(spec, toBuffer(data), 0, 0);
  }
  const spec = typeof type === "string" ? parseType(type) : type;
  return decodeAt(spec, toBuffer(data), 0, 0);
}

/** Decode a tuple of return values, in order. */
export function decodeParameters(types: (AbiTypeSpec | string)[], data: string | Uint8Array): DecodedValue[] {
  const specs = types.map((t) => (typeof t === "string" ? parseType(t) : t));
  const buf = toBuffer(data);
  return specs.map((spec, i) => decodeAt(spec, buf, 0, i * WORD));
}
