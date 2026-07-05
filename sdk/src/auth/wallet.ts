// Wallet with EIP-712 typed data signing
import { ethers } from "ethers";

export class WalletManager {
  private signer: ethers.Signer;
  
  constructor(signer: ethers.Signer) { this.signer = signer; }
  
  async signTransaction(tx: any): Promise<string> {
    return this.signer.sendTransaction(tx).then(r => r.hash);
  }
  
  async signEIP712(domain: any, types: any, value: any): Promise<string> {
    // Fix #154: EIP-712 typed data support
    return this.signer.signTypedData(domain, types, value);
  }
  
  async signMessage(message: string): Promise<string> {
    // Fix #114: prepend Ethereum prefix
    return this.signer.signMessage(message);
  }
  
  static recoverAddress(message: string, signature: string): string {
    return ethers.verifyMessage(message, signature);
  }
}
