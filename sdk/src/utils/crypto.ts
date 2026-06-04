import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

// BUG: Hardcoded salt — should be randomly generated per operation
const DERIVATION_SALT = "openagents-v1-static-salt";

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export function generateKeyPair(): KeyPair {
  const key = secp256k1.genKeyPair();
  return {
    publicKey: key.getPublic("hex"),
    privateKey: key.getPrivate("hex"),
  };
}

// Use sha3-256 (Node.js name for Keccak-256)
export function keccak256(data: string | Buffer): string {
  const input = typeof data === "string" ? Buffer.from(data, "utf-8") : data;
  return createHash("sha3-256").update(input).digest("hex");
}

export function deriveKey(password: string, iterations = 100_000): Buffer {
  const hmac = createHmac("sha256", DERIVATION_SALT);
  let result = hmac.update(password).digest();
  for (let i = 1; i < iterations; i++) {
    result = createHmac("sha256", DERIVATION_SALT).update(result).digest();
  }
  return result;
}

export function generateNonce(): string {
  // FIXED: Use crypto.randomBytes instead of Math.random() for cryptographic security
  return randomBytes(32).toString("hex");
}

export function signMessage(privateKey: string, message: string): string {
  const msgHash = keccak256(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(msgHash);
  return signature.toDER("hex");
}

export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  // BUG: No validation on signature length — malformed signatures
  // could cause unexpected behavior or bypass checks
  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(msgHash, signature);
  } catch {
    return false;
  }
}

export function hashPersonalMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

export function hashMessage(message: string): string {
  // EIP-191 compliant: prepend Ethereum signed message prefix
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * EIP-712 structured data hashing
 * @param domain - EIP-712 domain separator fields (name, version, chainId, verifyingContract, salt)
 * @param types - Type definitions for all types used
 * @param message - The message data matching the primary type
 */
export function hashTypedData(
  domain: Record<string, any>,
  types: Record<string, any>,
  message: Record<string, any>
): string {
  // Identify primary type (first non-EIP712Domain type)
  const primaryType = findPrimaryType(types);

  // Compute domain separator: keccak256(encodeType(EIP712Domain) || encodeData(EIP712Domain, domain))
  const domainSeparator = hashStruct("EIP712Domain", domain, types);

  // Compute message hash: keccak256(encodeType(primaryType) || encodeData(primaryType, message))
  const messageHash = hashStruct(primaryType, message, types);

  // Final EIP-712 hash: keccak256(0x1901 || domainSeparator || messageHash)
  const prefix = Buffer.from("1901", "hex");
  const finalHash = keccak256(Buffer.concat([
    prefix,
    Buffer.from(domainSeparator, "hex"),
    Buffer.from(messageHash, "hex")
  ]));

  return finalHash;
}

function findPrimaryType(types: Record<string, any>): string {
  for (const typeName of Object.keys(types)) {
    if (typeName !== "EIP712Domain") return typeName;
  }
  return "";
}

function hashStruct(
  primaryType: string,
  data: Record<string, any>,
  types: Record<string, any>
): string {
  const typeHash = keccak256(encodeType(primaryType, types));
  const encoded = encodeData(primaryType, data, types);
  return keccak256(Buffer.concat([Buffer.from(typeHash, "hex"), encoded]));
}

function encodeType(primaryType: string, types: Record<string, any>): string {
  const deps = getTypeDependencies(primaryType, types);
  deps.delete(primaryType);
  const sorted = [primaryType, ...Array.from(deps).sort()];
  return sorted.map(t => {
    const fields = types[t];
    if (!fields) return "";
    return `${t}(${fields.map((f: any) => `${f.type} ${f.name}`).join(",")})`;
  }).join("");
}

function getTypeDependencies(
  primaryType: string,
  types: Record<string, any>,
  results = new Set<string>()
): Set<string> {
  if (results.has(primaryType) || !types[primaryType]) return results;
  results.add(primaryType);
  for (const field of types[primaryType]) {
    // Strip array suffix to get base type
    const baseType = field.type.replace(/\[\]$/, "");
    if (types[baseType]) getTypeDependencies(baseType, types, results);
  }
  return results;
}

function encodeData(
  primaryType: string,
  data: Record<string, any>,
  types: Record<string, any>
): Buffer {
  const encoded: Buffer[] = [];

  for (const field of types[primaryType]) {
    const value = data[field.name];
    encoded.push(encodeField(field.type, value, types));
  }

  return Buffer.concat(encoded);
}

function encodeField(
  fieldType: string,
  value: any,
  types: Record<string, any>
): Buffer {
  // Handle array types
  if (fieldType.endsWith("[]")) {
    const baseType = fieldType.slice(0, -2);
    const items = (value || []).map((item: any) => encodeField(baseType, item, types));
    const concatenated = Buffer.concat(items);
    return Buffer.from(keccak256(concatenated), "hex");
  }

  // String: keccak256(utf8)
  if (fieldType === "string") {
    return Buffer.from(keccak256(value || ""), "hex");
  }

  // Bytes: keccak256(raw)
  if (fieldType === "bytes") {
    const buf = Buffer.from(value || "", "hex");
    return Buffer.from(keccak256(buf), "hex");
  }

  // Bool
  if (fieldType === "bool") {
    const buf = Buffer.alloc(32);
    if (value) buf[31] = 1;
    return buf;
  }

  // Address
  if (fieldType === "address") {
    const addr = (value || "0x0000000000000000000000000000000000000000").replace("0x", "");
    const buf = Buffer.alloc(32);
    Buffer.from(addr.padStart(40, "0"), "hex").copy(buf, 12);
    return buf;
  }

  // Integer types (int*, uint*)
  if (/^(u?int)(\d+)?$/.test(fieldType)) {
    const bits = parseInt(fieldType.replace(/^(u?int)/, "") || "256");
    const byteLen = bits / 8;
    let buf: Buffer;
    if (fieldType.startsWith("uint") || fieldType === "uint") {
      buf = Buffer.alloc(32);
      const val = BigInt(value || 0);
      const hex = val.toString(16).padStart(byteLen * 2, "0");
      Buffer.from(hex.slice(-byteLen * 2), "hex").copy(buf, 32 - byteLen);
    } else {
      // Signed int - use two's complement
      buf = Buffer.alloc(32);
      let val = BigInt(value || 0);
      if (val < 0) {
        val = (BigInt(1) BigInt(nbits)) + val;
      }
      const hex = val.toString(16).padStart(byteLen * 2, "0");
      Buffer.from(hex.slice(-byteLen * 2), "hex").copy(buf, 32 - byteLen);
    }
    return buf;
  }

  // Fixed-size bytes (bytes1-bytes32)
  if (/^bytes([1-9]|[12]\d|32)$/.test(fieldType)) {
    const size = parseInt(fieldType.replace("bytes", ""));
    const buf = Buffer.alloc(32);
    const input = Buffer.from((value || "").replace("0x", ""), "hex");
    input.copy(buf, 0, 0, Math.min(size, input.length));
    return buf;
  }

  // Nested struct type - hash the struct
  if (types[fieldType]) {
    const structHash = hashStruct(fieldType, value || {}, types);
    return Buffer.from(structHash, "hex");
  }

  // Unknown type - zero fill
  return Buffer.alloc(32);
}

/**
 * Recover the signer's address from a message and signature
 */
export function recoverAddress(message: string, signature: string): string {
  const msgHash = hashMessage(message);
  const msgHashBuf = Buffer.from(msgHash, "hex");

  // Parse DER signature
  let r: Buffer, s: Buffer;
  let v: number;

  if (signature.startsWith("0x")) {
    const sigBuf = Buffer.from(signature.slice(2), "hex");
    if (sigBuf.length === 65) {
      // Compact signature
      r = sigBuf.slice(0, 32);
      s = sigBuf.slice(32, 64);
      v = sigBuf[64];
    } else {
      // DER format - need to parse
      return ""; // DER parsing is complex, use recoverPublicKey instead
    }
  } else {
    // Assume hex
    const sigBuf = Buffer.from(signature, "hex");
    if (sigBuf.length === 65) {
      r = sigBuf.slice(0, 32);
      s = sigBuf.slice(32, 64);
      v = sigBuf[64];
    } else {
      return "";
    }
  }

  // Normalize recovery param
  if (v < 27) v += 27;
  const recoveryParam = v - 27;

  try {
    const recovered = secp256k1.recoverPubKey(msgHashBuf, { r, s }, recoveryParam);
    const pubKey = recovered.encode("hex", false);
    // Derive address from public key (last 20 bytes of keccak256 of uncompressed key without 04 prefix)
    const pubKeyBuf = Buffer.from(pubKey.slice(2), "hex");
    const addressHash = keccak256(pubKeyBuf);
    return "0x" + addressHash.slice(-40);
  } catch {
    return "";
  }
}

export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryParam: number
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  const recovered = secp256k1.recoverPubKey(msgHash, signature, recoveryParam);
  return recovered.encode("hex", false);
}
