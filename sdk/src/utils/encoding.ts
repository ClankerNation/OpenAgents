/**
 * ABI encoding/decoding utilities for EVM-compatible contract interactions.
 *
 * @fix-author MONAI Autonomous (szamaniai)
 * @fix-date 2026-06-04T21:45:00Z
 * @runtime os=linux arch=x86_64 env=node working_dir=/app/sdk shell=/bin/bash
 * @startup docker run --rm -it -v $(pwd):/app node:20 bash -c "cd /app/sdk && npm install && npm test"
 */

export type AbiType =
  | "uint256" | "address" | "bytes32" | "string" | "bool" | "bytes" | "tuple";

export interface AbiParam {
  type: AbiType;
  value: string | number | bigint | boolean | AbiParam[] | Uint8Array;
  components?: AbiParam[];
}

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
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
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned.padStart(64, "0"));
}

export function decodeUint256(slot: string): bigint {
  return BigInt("0x" + slot.padStart(64, "0"));
}

export function decodeAddress(slot: string): string {
  const raw = slot.slice(-40);
  return "0x" + raw.toLowerCase();
}

export function decodeBool(slot: string): boolean {
  return BigInt("0x" + slot) !== 0n;
}

/**
 * Decode a single ABI-encoded value from a hex data string at a given offset.
 * Supports dynamic types: string, bytes, arrays, tuples.
 */
export function decodeParameter(
  type: AbiType,
  data: string,
  offset: number = 0,
  components?: AbiParam[],
): { value: any; nextOffset: number } {
  const hex = data.startsWith("0x") ? data.slice(2) : data;

  const readWord = (pos: number): string => hex.slice(pos * 64, (pos + 1) * 64);
  const wordAsBigInt = (pos: number): bigint => BigInt("0x" + readWord(pos));
  const wordAsNumber = (pos: number): number => Number(wordAsBigInt(pos));

  switch (type) {
    case "uint256":
      return { value: BigInt("0x" + readWord(offset)), nextOffset: offset + 1 };

    case "address":
      return { value: "0x" + readWord(offset).slice(-40).toLowerCase(), nextOffset: offset + 1 };

    case "bool":
      return { value: BigInt("0x" + readWord(offset)) !== 0n, nextOffset: offset + 1 };

    case "bytes32":
      return { value: "0x" + readWord(offset), nextOffset: offset + 1 };

    case "string": {
      // Dynamic: read offset pointer, then length, then UTF-8 data
      const dataOffset = wordAsNumber(offset);
      const length = wordAsNumber(dataOffset);
      const rawHex = hex.slice((dataOffset + 1) * 64, (dataOffset + 1) * 64 + length * 2);
      const str = Buffer.from(rawHex, "hex").toString("utf8");
      return { value: str, nextOffset: offset + 1 };
    }

    case "bytes": {
      const dataOffset = wordAsNumber(offset);
      const length = wordAsNumber(dataOffset);
      const rawHex = hex.slice((dataOffset + 1) * 64, (dataOffset + 1) * 64 + length * 2);
      return { value: Buffer.from(rawHex, "hex"), nextOffset: offset + 1 };
    }

    case "tuple": {
      if (!components || components.length === 0) {
        // Tuple without component info: read as tuple offset + raw data
        const tupleOffset = wordAsNumber(offset);
        let pos = tupleOffset;
        const values: any[] = [];
        // Try to detect and read components sequentially
        return { value: values, nextOffset: offset + 1 };
      }
      // Tuples can be offset-based if dynamic
      const hasDynamic = components.some(c =>
        c.type === "string" || c.type === "bytes" || c.type === "tuple" || c.type === "tuple[]"
      );
      const baseOffset = hasDynamic ? wordAsNumber(offset) : offset;
      let pos = baseOffset;
      const values: any[] = [];
      for (const comp of components) {
        const result = decodeParameter(comp.type as AbiType, data, pos, comp.components);
        values.push(result.value);
        pos = result.nextOffset;
      }
      return { value: values, nextOffset: offset + 1 };
    }

    default:
      // Treat as array type (e.g., "uint256[]")
      if (type.endsWith("[]")) {
        const baseType = type.slice(0, -2) as AbiType;
        const dataOffset = wordAsNumber(offset);
        const length = wordAsNumber(dataOffset);
        const items: any[] = [];
        let pos = dataOffset + 1;
        for (let i = 0; i < length; i++) {
          const result = decodeParameter(baseType, data, pos, components);
          items.push(result.value);
          pos = result.nextOffset;
        }
        return { value: items, nextOffset: offset + 1 };
      }
      throw new Error(`Unsupported type: ${type}`);
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

