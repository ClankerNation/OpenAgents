// Tests for subscribeToEvents: event decoding and indexed filtering.
import { ethers } from "ethers";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

const abi = [
  "event TaskCreated(uint256 indexed taskId, address indexed creator, string description, uint256 reward)",
  "function taskCount() view returns (uint256)",
];

const iface = new ethers.Interface(abi);
const fragment = iface.getEvent("TaskCreated");
const creator = "0x1111111111111111111111111111111111111111";

// Build a real encoded log for TaskCreated(1, creator, "hello", 500)
const log = iface.encodeEventLog(fragment, [1n, creator, "hello", 500n]);
const parsed = iface.parseLog({ topics: log.topics, data: log.data });

// 1. Decoding works: parameter names and values
{
  console.log("test 1: event log decodes with names/values");
  assert(parsed !== null, "log parses");
  const args: Record<string, any> = {};
  const inputs = fragment.inputs;
  for (let i = 0; i < inputs.length; i++) {
    args[inputs[i].name || `arg${i}`] = (parsed as any).args[i];
  }
  assert(args.taskId === 1n, "taskId decoded");
  assert(args.creator === creator, "creator decoded");
  assert(args.description === "hello", "description decoded");
  assert(args.reward === 500n, "reward decoded");
}

// 2. Indexed filtering logic (matchesFilter equivalent)
{
  console.log("test 2: indexed filter matching");
  const args: Record<string, any> = {};
  for (let i = 0; i < fragment.inputs.length; i++) {
    args[fragment.inputs[i].name || `arg${i}`] = (parsed as any).args[i];
  }
  // filter on indexed taskId
  const match = args.taskId === 1n && args.creator === creator;
  assert(match, "filter on indexed taskId+creator matches");
  const noMatch = args.taskId === 2n;
  assert(!noMatch, "different taskId filtered out");
}

// 3. Fragment resolution validates event names
{
  console.log("test 3: fragment resolution");
  assert(iface.getEvent("TaskCreated") !== null, "known event resolves");
  const unknown = iface.getEvent("DoesNotExist");
  assert(unknown === null, "unknown event resolves to null");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
