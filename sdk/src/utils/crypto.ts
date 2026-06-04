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
  // BUG: Math.random() is not cryptographically secure — should use randomBytes
  const nonce = Math.random().toString(36).substring(2, 15) +
    Math.random().toString(36).substring(2, 15);
  return nonce;
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
  // Prepend Ethereum signed message prefix per EIP-191
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

export function hashTypedData(domain: Record<string, any>, types: Record<string, any>, message: Record<string, any>): string {
  // EIP-712 structured data hashing
  // Encode type hash
  const primaryType = Object.keys(types).find(t => t !== 'EIP712Domain') || '';
  const typeHash = keccak256(encodeType(primaryType, types));
  
  // Encode data
  const encodedData = encodeData(primaryType, message, types);
  
  // Return final hash
  return keccak256(Buffer.concat([
    Buffer.from('1901', 'hex'),
    typeHash,
    encodedData
  ]));
}

function encodeType(primaryType: string, types: Record<string, any>): string {
  const deps = getTypeDependencies(primaryType, types);
  deps.delete(primaryType);
  const sorted = [primaryType, ...Array.from(deps).sort()];
  return sorted.map(t => `${t}(${types[t].map((f: any) => `${f.type} ${f.name}`).join(',')})`).join('');
}

function getTypeDependencies(primaryType: string, types: Record<string, any>, results = new Set<string>()): Set<string> {
  if (results.has(primaryType) || !types[primaryType]) return results;
  results.add(primaryType);
  for (const field of types[primaryType]) {
    const baseType = field.type.replace(/\[\]$/, '');
    if (types[baseType]) getTypeDependencies(baseType, types, results);
  }
  return results;
}

function encodeData(primaryType: string, data: Record<string, any>, types: Record<string, any>): Buffer {
  const encoded: Buffer[] = [];
  for (const field of types[primaryType]) {
    const value = data[field.name];
    if (field.type === 'string') {
      encoded.push(Buffer.from(keccak256(value), 'hex'));
    } else if (field.type === 'bytes') {
      encoded.push(Buffer.from(keccak256(value), 'hex'));
    } else if (field.type === 'bool') {
      encoded.push(Buffer.from(keccak256(value ? 'true' : 'false'), 'hex'));
    } else if (field.type === 'address') {
      encoded.push(Buffer.from(value.toLowerCase().padStart(64, '0'), 'hex'));
    } else if (field.type.endsWith('[]')) {
      const baseType = field.type.slice(0, -2);
      const items = value.map((v: any) => encodeData(baseType, { [baseType]: v }, { [baseType]: types[baseType] }));
      encoded.push(Buffer.from(keccak256(Buffer.concat(items)), 'hex'));
    } else if (types[field.type]) {
      encoded.push(Buffer.from(encodeData(field.type, value, types), 'hex'));
    } else {
      // uint/int types - encode as 32-byte hex
      const num = BigInt(value);
      const hex = (num < 0 ? (BigInt(1) << BigInt(256)) + num : num).toString(16).padStart(64, '0');
      encoded.push(Buffer.from(hex, 'hex'));
    }
  }
  return Buffer.concat(encoded);
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
