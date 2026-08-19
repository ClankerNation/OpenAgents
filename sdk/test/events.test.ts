/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
import { expect } from "chai";
import { ethers } from "hardhat";
import { OpenAgentsSDK } from "../src/index";

describe("OpenAgentsSDK Event Subscription", function () {
  it("should have subscribeToEvents method", function () {
    const sdk = new OpenAgentsSDK({
      name: "test",
      endpoint: "http://localhost",
      privateKey: "0x" + "1".repeat(64),
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });
    
    expect(sdk.subscribeToEvents).to.be.a("function");
  });
});
