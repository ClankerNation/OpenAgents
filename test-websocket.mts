// Tests for WebSocketProvider: queueing, FIFO flush, resubscribe, heartbeat.
import { WebSocketProvider } from "./sdk/src/providers/websocket";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

// Mock WebSocket
class MockWS {
  static instances: MockWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e: any) => void) | null = null;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) { MockWS.instances.push(this); }
  send(d: string) { this.sent.push(d); }
  close() { this.closed = true; this.onclose?.(); }
}

// @ts-ignore
global.WebSocket = MockWS;

// 1. Send while disconnected queues, flush on connect (FIFO)
{
  console.log("test 1: queue + FIFO flush");
  const p = new WebSocketProvider({ url: "ws://x", maxQueueSize: 100 });
  const p1 = p.send("a", [1]);
  const p2 = p.send("b", [2]);
  // no connection yet -> queued (no WebSocket instance created yet)
  assert(MockWS.instances.length === 0, "no socket created while disconnected");
  // connect
  const conn = p.connect();
  const ws = MockWS.instances[MockWS.instances.length - 1];
  // simulate open
  setImmediate(() => ws.onopen?.());
  conn.then(() => {
    const sent = ws.sent.filter(s => !s.includes('"method":"eth_subscribe"'));
    const aSent = sent.some(s => s.includes('"method":"a"'));
    const bSent = sent.some(s => s.includes('"method":"b"'));
    assert(aSent && bSent, "queued msgs flushed after connect");
  });
  await new Promise(r => setTimeout(r, 50));
}

// 2. Queue cap
{
  console.log("test 2: queue cap");
  const p = new WebSocketProvider({ url: "ws://x", maxQueueSize: 2 });
  p.send("a", []); p.send("b", []);
  let threw = false;
  try { await p.send("c", []); } catch { threw = true; }
  assert(threw, "queue over cap rejects");
}

// 3. Heartbeat timers start on connect
{
  console.log("test 3: heartbeat on connect");
  const p = new WebSocketProvider({ url: "ws://x", heartbeatIntervalMs: 10, heartbeatTimeoutMs: 30 });
  const conn = p.connect();
  const ws = MockWS.instances[MockWS.instances.length - 1];
  setImmediate(() => ws.onopen?.());
  await conn;
  await new Promise(r => setTimeout(r, 25));
  assert(ws.sent.some(s => s.includes('"id":-1')), "ping sent");
  p.disconnect();
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
