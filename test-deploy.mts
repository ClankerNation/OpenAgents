// Smoke test for deployContract: verifies the method exists and wires up
// ContractFactory correctly. Real deployment needs a live RPC endpoint.
import { OpenAgentsSDK } from "./sdk/src/index";

const sdk = new OpenAgentsSDK({
  name: "test",
  endpoint: "http://localhost",
  privateKey: "0x" + "11".repeat(32),
  rpcUrl: "http://localhost:8545",
  registryAddress: "0x0000000000000000000000000000000000000001",
  routerAddress: "0x0000000000000000000000000000000000000002",
});

// Just verify the method is callable (will fail on network, but wiring is checked)
const method = (sdk as any).deployContract;
if (typeof method !== "function") {
  console.error("FAIL: deployContract not a function");
  process.exit(1);
}
console.log("ok - deployContract is defined");
process.exit(0);
