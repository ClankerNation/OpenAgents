from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RPC = ROOT / "sdk" / "src" / "providers" / "rpc.ts"
RETRY = ROOT / "sdk" / "src" / "utils" / "retry.ts"


def read(path: Path) -> str:
    return path.read_text()


def test_rpc_provider_uses_abort_controller_timeout():
    src = read(RPC)
    assert "DEFAULT_TIMEOUT_MS = 30_000" in src
    assert "new AbortController()" in src
    assert "setTimeout(() => controller.abort(), this.timeoutMs)" in src
    assert "signal: controller.signal" in src
    assert "RpcTimeoutError" in src


def test_rpc_provider_rejects_http_and_typed_json_rpc_errors():
    src = read(RPC)
    assert "if (!res.ok)" in src
    assert "throw new RpcHttpError(res.status)" in src
    assert "RpcResponseError" in src
    assert "Invalid JSON-RPC error shape" in src
    assert "Unexpected RPC response id" in src


def test_batch_has_size_and_gas_limits_before_network_call():
    src = read(RPC)
    assert "DEFAULT_MAX_BATCH_SIZE = 100" in src
    assert "DEFAULT_MAX_BATCH_GAS = 30_000_000n" in src
    assert "this.validateBatch(calls);" in src
    assert "calls.length > this.maxBatchSize" in src
    assert "gasBudget > this.maxBatchGas" in src


def test_batch_preserves_request_order_by_id_not_response_sorting():
    src = read(RPC)
    assert "const byId = new Map<number, JsonRpcResponse>();" in src
    assert "return requests.map((request) =>" in src
    assert "Missing RPC response for request" in src
    assert ".sort((a, b) => a.id - b.id)" not in src


def test_retry_is_bounded_and_limited_to_retryable_statuses():
    src = read(RETRY)
    assert "maxRetries: 3" in src
    assert "retryableStatusCodes: [429, 503]" in src
    assert "Math.min(Math.floor(merged.maxRetries), 10)" in src
    assert "!this.isRetryable(lastError)" in src
    assert "this.consecutiveFailures = 0" in src


def test_private_runtime_context_is_not_disclosed():
    combined = read(RPC) + "\n" + read(RETRY)
    assert "session_initialization_context: Not disclosed" in combined
    assert "Knowledge cutoff" not in combined
    assert "MEMORY (your personal notes)" not in combined
