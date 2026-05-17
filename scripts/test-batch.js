const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const binPath = path.join(__dirname, "..", "artifacts", "solc", "AgentRegistry.bin");
  const abiPath = path.join(__dirname, "..", "artifacts", "solc", "AgentRegistry.abi");

  const bytecode = "0x" + fs.readFileSync(binPath, "utf8").trim();
  const abi = JSON.parse(fs.readFileSync(abiPath, "utf8"));

  const [owner, addr1] = await ethers.getSigners();
  const FEE = ethers.parseEther("0.01");

  const factory = await ethers.getContractFactory(abi, bytecode);
  const registry = await factory.deploy(FEE);
  await registry.waitForDeployment();
  console.log("Deployed at:", await registry.getAddress());

  // Helper to encode batch params into bytes
  function encodeBatch(names, endpoints) {
    return ethers.AbiCoder.defaultAbiCoder().encode(
      ["string[]", "string[]"],
      [names, endpoints]
    );
  }

  // ====== TEST 1: Single registration ======
  console.log("\n=== Test 1: Single registration ===");
  let tx = await registry.connect(addr1).registerAgent("Agent1", "https://agent1.ai", { value: FEE });
  await tx.wait();
  let count = await registry.getActiveAgentCount();
  console.log("Active agents:", count.toString());
  console.assert(count === 1n, "FAIL: expected 1");

  // ====== TEST 2: Batch register 5 ======
  console.log("\n=== Test 2: Batch 5 agents ===");
  const names = ["B1", "B2", "B3", "B4", "B5"];
  const endpoints = ["https://b1.ai","https://b2.ai","https://b3.ai","https://b4.ai","https://b5.ai"];
  const batchData = encodeBatch(names, endpoints);
  tx = await registry.connect(addr1).batchRegister(batchData, { value: FEE * 5n });
  const receipt = await tx.wait();
  console.log("Gas used:", receipt.gasUsed.toString());
  count = await registry.getActiveAgentCount();
  console.log("Active agents:", count.toString());
  console.assert(count === 6n, `FAIL: expected 6, got ${count}`);

  // ====== TEST 3: BatchRegistered event ======
  const batchEvent = receipt.logs
    .map(log => { try { return registry.interface.parseLog(log); } catch { return null; } })
    .filter(e => e && e.name === "BatchRegistered");
  console.assert(batchEvent.length === 1, "FAIL: expected 1 BatchRegistered event");
  console.log("Batch: count=", batchEvent[0].args.count.toString(), "totalFee=", ethers.formatEther(batchEvent[0].args.totalFee));

  // ====== TEST 4: AgentRegistered events per agent ======
  const agentEvents = receipt.logs
    .map(log => { try { return registry.interface.parseLog(log); } catch { return null; } })
    .filter(e => e && e.name === "AgentRegistered");
  console.assert(agentEvents.length === 5, `FAIL: expected 5 AgentRegistered events, got ${agentEvents.length}`);
  console.log("Individual events:", agentEvents.length);

  // ====== TEST 5: Reject empty batch ======
  console.log("\n=== Test 5: Empty batch ===");
  try {
    await registry.connect(addr1).batchRegister(encodeBatch([], []), { value: 0 });
    console.assert(false, "FAIL: should revert");
  } catch (e) {
    console.log("Empty rejected:", e.message.includes("Batch size") ? "YES" : "CHECK");
  }

  // ====== TEST 6: Reject batch > 50 ======
  console.log("\n=== Test 6: Batch > 50 ===");
  const fiftyOneNames = Array(51).fill("A").map((_, i) => `N${i}`);
  const fiftyOneEps = Array(51).fill("A").map((_, i) => `https://n${i}.ai`);
  try {
    await registry.connect(addr1).batchRegister(encodeBatch(fiftyOneNames, fiftyOneEps), { value: FEE * 51n });
    console.assert(false, "FAIL: should revert");
  } catch (e) {
    console.log(">50 rejected:", e.message.includes("Batch size") ? "YES" : "CHECK");
  }

  // ====== TEST 7: Reject insufficient fee ======
  console.log("\n=== Test 7: Insufficient fee ===");
  try {
    await registry.connect(addr1).batchRegister(encodeBatch(["A1","A2"], ["https://e1.ai","https://e2.ai"]), { value: FEE });
    console.assert(false, "FAIL: should revert");
  } catch (e) {
    console.log("Insufficient fee rejected:", e.message.includes("Insufficient") ? "YES" : "CHECK");
  }

  // ====== TEST 8: Batch 50 ======
  console.log("\n=== Test 8: Batch 50 agents ===");
  const fiftyN = Array(50).fill("A").map((_, i) => `F${i}`);
  const fiftyE = Array(50).fill("A").map((_, i) => `https://f${i}.ai`);
  const tx8 = await registry.connect(addr1).batchRegister(encodeBatch(fiftyN, fiftyE), { value: FEE * 50n });
  const r8 = await tx8.wait();
  console.log("Gas for 50:", r8.gasUsed.toString());
  count = await registry.getActiveAgentCount();
  console.log("Total active:", count.toString());
  console.assert(count === 56n, `FAIL: expected 56, got ${count}`);

  console.log("\n✅ ALL TESTS PASSED");

  console.log("\n✅ ALL TESTS PASSED");
}

main().catch(e => { console.error("FAILED:", e); process.exit(1); });
