// Crypto utilities with secp256k1 and Ethereum prefix
import { ethers } from "ethers";

export function hashMessage(message: string): string {
  // Fix #114: prepend Ethereum prefix
  return ethers.hashMessage(message);
}

export function recoverPublicKey(signature: string, messageHash: string): string {
  // Fix #136: secp256k1 key recovery
  const recovered = ethers.recoverAddress(messageHash, signature);
  return recovered;
}

export function verifySignature(message: string, signature: string, expectedAddress: string): boolean {
  const recovered = ethers.verifyMessage(message, signature);
  return recovered.toLowerCase() === expectedAddress.toLowerCase();
}
