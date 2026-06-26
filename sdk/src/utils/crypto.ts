import { keccak256, toUtf8Bytes, concat } from "ethers";

/**
 * Hashes a message with the Ethereum Signed Message prefix,
 * making it fully compatible with on-chain ecrecover.
 */
export function hashMessage(message: string | Uint8Array): string {
  const messageBytes = typeof message === "string" ? toUtf8Bytes(message) : message;
  
  // Standard Ethereum Signed Message prefix: \x19Ethereum Signed Message:\n + message.length
  const prefix = `\x19Ethereum Signed Message:\n${messageBytes.length}`;
  const prefixBytes = toUtf8Bytes(prefix);
  
  // Concatenate prefix and raw message bytes, then compute keccak256
  const finalBytes = concat([prefixBytes, messageBytes]);
  return keccak256(finalBytes);
}

/**
 * Hashes typed EIP-712 data (useful for domain separation).
 */
export function hashTypedData(domain: any, types: any, value: any): string {
  return keccak256(toUtf8Bytes(JSON.stringify({ domain, types, value })));
}
