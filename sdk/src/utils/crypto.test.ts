import assert from "node:assert/strict";
import {
  hashMessage as ethersHashMessage,
  TypedDataEncoder,
  Wallet,
} from "ethers";
import {
  hashMessage,
  hashPersonalMessage,
  hashTypedData,
  recoverAddress,
  recoverTypedDataAddress,
} from "./crypto";

const PRIVATE_KEY =
  "0x59c6995e998f97a5a004497e5da13d15f8c61e63b6b54f5c7e9f3414d8280d5a";

async function testEip191Hash(): Promise<void> {
  const message = "OpenAgents signed message";
  const expected = ethersHashMessage(message).slice(2);

  assert.equal(hashMessage(message), expected);
  assert.equal(hashPersonalMessage(message), expected);
}

async function testRecoverPersonalMessageAddress(): Promise<void> {
  const wallet = new Wallet(PRIVATE_KEY);
  const message = "recover me";
  const signature = await wallet.signMessage(message);

  assert.equal(recoverAddress(message, signature), wallet.address);
  assert.equal(
    recoverAddress(hashMessage(message), signature, { prehashed: true }),
    wallet.address
  );
}

async function testTypedDataHashAndRecover(): Promise<void> {
  const wallet = new Wallet(PRIVATE_KEY);
  const domain = {
    name: "OpenAgents",
    version: "1",
    chainId: 1,
    verifyingContract: "0x0000000000000000000000000000000000000001",
  };
  const types = {
    Task: [
      { name: "agent", type: "address" },
      { name: "reward", type: "uint256" },
      { name: "memo", type: "string" },
    ],
  };
  const value = {
    agent: wallet.address,
    reward: 10n,
    memo: "ship it",
  };

  assert.equal(
    hashTypedData(domain, types, value),
    TypedDataEncoder.hash(domain, types, value).slice(2)
  );

  const signature = await wallet.signTypedData(domain, types, value);
  assert.equal(
    recoverTypedDataAddress(domain, types, value, signature),
    wallet.address
  );
}

async function main(): Promise<void> {
  await testEip191Hash();
  await testRecoverPersonalMessageAddress();
  await testTypedDataHashAndRecover();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
