import re

with open('sdk/src/utils/encoding.ts', 'r') as f:
    content = f.read()

header = """/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
"""
if not content.startswith("/**\n * @contributor-info"):
    content = re.sub(r'^/\*\*.*?\*/\s*', '', content, flags=re.DOTALL)
    content = header + content

# Update AbiType
content = content.replace(
    'export type AbiType = "uint256" | "address" | "bytes32" | "string" | "bool";',
    'export type AbiType = "uint256" | "int256" | "address" | "bytes32" | "string" | "bool";'
)

# Fix encodeUint256
old_encode_uint = """export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  // BUG: No overflow check — values > 2^256-1 silently wrap/truncate
  return n.toString(16).padStart(64, "0");
}"""

new_encode_uint = """const MAX_UINT256 = (1n << 256n) - 1n;
const MAX_INT256 = (1n << 255n) - 1n;
const MIN_INT256 = -(1n << 255n);

export function encodeUint256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < 0n || n > MAX_UINT256) {
    throw new Error("encodeUint256: value out of bounds (must be >= 0 and < 2^256)");
  }
  return n.toString(16).padStart(64, "0");
}

export function encodeInt256(value: bigint | number): string {
  const n = BigInt(value);
  if (n < MIN_INT256 || n > MAX_INT256) {
    throw new Error("encodeInt256: value out of bounds");
  }
  if (n >= 0n) {
    return n.toString(16).padStart(64, "0");
  }
  // Two's complement for negative numbers
  const twosComplement = (1n << 256n) + n;
  return twosComplement.toString(16).padStart(64, "0");
}"""
content = content.replace(old_encode_uint, new_encode_uint)

# Fix encodeParams to include int256
old_encode_params_loop = """      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number));
        break;"""
new_encode_params_loop = """      case "uint256":
        encoded += encodeUint256(BigInt(param.value as number));
        break;
      case "int256":
        encoded += encodeInt256(BigInt(param.value as number));
        break;"""
content = content.replace(old_encode_params_loop, new_encode_params_loop)

# Fix decodeHex
old_decode_hex = """export function decodeHex(hex: string): bigint {
  // BUG: Doesn't validate "0x" prefix — a bare decimal string like "255"
  // would be parsed as hex 0x255 = 597, silently returning wrong value
  const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
  return BigInt("0x" + cleaned);
}"""
new_decode_hex = """export function decodeHex(hex: string): bigint {
  if (!hex.startsWith("0x")) {
    throw new Error("decodeHex: missing 0x prefix");
  }
  return BigInt(hex);
}"""
content = content.replace(old_decode_hex, new_decode_hex)

# Fix decodeUint256
old_decode_uint = """export function decodeUint256(slot: string): bigint {
  // BUG: Doesn't handle short values — if slot is less than 64 chars,
  // no left-padding is applied before parsing, giving wrong results
  return BigInt("0x" + slot);
}"""
new_decode_uint = """export function decodeUint256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeUint256: missing 0x prefix");
  }
  const padded = "0x" + slot.slice(2).padStart(64, "0");
  return BigInt(padded);
}

export function decodeInt256(slot: string): bigint {
  if (!slot.startsWith("0x")) {
    throw new Error("decodeInt256: missing 0x prefix");
  }
  const padded = "0x" + slot.slice(2).padStart(64, "0");
  const n = BigInt(padded);
  if (n >= (1n << 255n)) {
    return n - (1n << 256n);
  }
  return n;
}"""
content = content.replace(old_decode_uint, new_decode_uint)

with open('sdk/src/utils/encoding.ts', 'w') as f:
    f.write(content)

print("Patched encoding.ts")
