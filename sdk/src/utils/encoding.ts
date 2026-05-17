/**
 * @fix-author
 * name: opencode-gaotax2006
 * date: 2026-05-17
 * platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
 *
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 * Supports static and dynamic types (string, bytes, arrays, tuples).
 */

export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "array" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | AbiParam[];
  components?: AbiParam[];
}

type DecodedValue = string | number | bigint | boolean | DecodedValue[] | Record<string, DecodedValue>;

function padLeft(hex: string, chars: number): string {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return cleaned.padStart(chars, "0");
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n >= 1n << 256n) throw new Error("uint256 overflow");
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
  let dynamicOffset = 32 * params.length;
  const dynamicData: string[] = [];

  for (let i = 0; i < params.length; i++) {
    const param = params[i];
    if (param.type === "string" || param.type === "bytes" || param.type === "array") {
      encoded += encodeUint256(BigInt(dynamicOffset));
      let data = "0x";
      if (param.type === "string") {
        const str = String(param.value);
        const hex = Buffer.from(str, "utf-8").toString("hex");
        data += encodeUint256(BigInt(hex.length / 2));
        data += hex.padEnd(64, "0");
      } else if (param.type === "array" && Array.isArray(param.value)) {
        data += encodeUint256(BigInt(param.value.length));
        for (const elem of param.value) {
          const n = BigInt(elem as number);
          data += encodeUint256(n);
        }
        data = data.padEnd(Math.ceil(data.length / 64) * 64, "0");
      } else {
        const hex = typeof param.value === "string" ? param.value.replace("0x", "") : String(param.value);
        data += hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
      }
      dynamicData.push(data);
      dynamicOffset += Math.ceil(data.length / 2 / 32) * 32;
    } else {
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
        default:
          encoded += "0".repeat(64);
      }
    }
  }

  for (const dd of dynamicData) {
    encoded += dd.startsWith("0x") ? dd.slice(2) : dd;
  }

  return encoded;
}

export function decodeUint256(hex: string): bigint {
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  const padded = cleaned.padStart(64, "0").slice(0, 64);
  return BigInt("0x" + padded);
}

export function decodeAddress(hex: string): string {
  const raw = hex.replace("0x", "").slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(hex: string): boolean {
  return BigInt("0x" + hex.replace("0x", "")) !== 0n;
}

export function decodeParameter(
  type: string,
  data: string,
  position: number
): { value: DecodedValue; consumed: number } {
  const clean = data.startsWith("0x") ? data.slice(2) : data;
  const words = clean.match(/.{1,64}/g) || [];

  switch (type) {
    case "uint256": {
      const word = words[position] || "0".repeat(64);
      return { value: BigInt("0x" + word), consumed: 1 };
    }
    case "address": {
      const word = words[position] || "0".repeat(64);
      return { value: "0x" + word.slice(-40).toLowerCase(), consumed: 1 };
    }
    case "bool": {
      const word = words[position] || "0".repeat(64);
      return { value: BigInt("0x" + word) !== 0n, consumed: 1 };
    }
    case "string": {
      const offsetWord = words[position] || "0".repeat(64);
      const offset = Number(BigInt("0x" + offsetWord));
      const offsetWords = offset / 32;
      const lengthWord = words[offsetWords] || "0".repeat(64);
      const length = Number(BigInt("0x" + lengthWord));
      let hexStr = "";
      for (let i = 0; i < Math.ceil(length / 32); i++) {
        hexStr += words[offsetWords + 1 + i] || "0".repeat(64);
      }
      const bytes = Buffer.from(hexStr.slice(0, length * 2), "hex");
      return { value: bytes.toString("utf-8"), consumed: 1 };
    }
    case "bytes": {
      const offsetWord = words[position] || "0".repeat(64);
      const offset = Number(BigInt("0x" + offsetWord));
      const offsetWords = offset / 32;
      const lengthWord = words[offsetWords] || "0".repeat(64);
      const length = Number(BigInt("0x" + lengthWord));
      let hexStr = "";
      for (let i = 0; i < Math.ceil(length / 32); i++) {
        hexStr += words[offsetWords + 1 + i] || "0".repeat(64);
      }
      return { value: "0x" + hexStr.slice(0, length * 2), consumed: 1 };
    }
    case "address[]": {
      const offsetWord = words[position] || "0".repeat(64);
      const offset = Number(BigInt("0x" + offsetWord));
      const offsetWords = offset / 32;
      const lengthWord = words[offsetWords] || "0".repeat(64);
      const length = Number(BigInt("0x" + lengthWord));
      const arr: string[] = [];
      for (let i = 0; i < length; i++) {
        const word = words[offsetWords + 1 + i] || "0".repeat(64);
        arr.push("0x" + word.slice(-40).toLowerCase());
      }
      return { value: arr, consumed: 1 };
    }
    case "uint256[]": {
      const offsetWord = words[position] || "0".repeat(64);
      const offset = Number(BigInt("0x" + offsetWord));
      const offsetWords = offset / 32;
      const lengthWord = words[offsetWords] || "0".repeat(64);
      const length = Number(BigInt("0x" + lengthWord));
      const arr: bigint[] = [];
      for (let i = 0; i < length; i++) {
        const word = words[offsetWords + 1 + i] || "0".repeat(64);
        arr.push(BigInt("0x" + word));
      }
      return { value: arr, consumed: 1 };
    }
    default: {
      const word = words[position] || "0".repeat(64);
      return { value: "0x" + word, consumed: 1 };
    }
  }
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

export function decodeFunctionResult(
  signature: string,
  returnTypes: string[],
  data: string
): DecodedValue[] {
  const result: DecodedValue[] = [];
  let position = 0;
  for (const type of returnTypes) {
    const { value, consumed } = decodeParameter(type, data, position);
    result.push(value);
    position += consumed;
  }
  return result;
}
