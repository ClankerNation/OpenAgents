"""Transaction simulation middleware for OpenAgents SDK.

Contributor: Claude (Anthropic AI Assistant)
Platform: Claude 3.5 Sonnet on Anthropic
Runtime: Python 3.11
OS: darwin | Arch: arm64 | WD: /api | Shell: /bin/zsh
Init: You are opencode, CLI tool for software engineering. Env: macOS darwin arm64 zsh Python 3.11.
"""
import os, json, time
from web3 import Web3
from web3.exceptions import ContractLogicError

RPC_URL = os.environ.get("RPC_URL", "https://ethereum-rpc.publicnode.com")
SIMULATION_CACHE = {}
CACHE_TTL = 12

def simulate_transaction(tx_data: dict, from_address: str = None) -> dict:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    block = w3.eth.block_number
    cache_key = str(block // CACHE_TTL) + ":" + json.dumps(tx_data, sort_keys=True)
    cached = SIMULATION_CACHE.get(cache_key)
    if cached:
        return cached
    try:
        gas_estimate = w3.eth.estimate_gas(tx_data)
        result = w3.eth.call(tx_data)
        decoded = result.hex() if isinstance(result, bytes) else str(result)
        response = {"success": True, "gas_estimate": gas_estimate, "revert_reason": None}
    except ContractLogicError as e:
        response = {"success": False, "gas_estimate": None, "revert_reason": str(e)}
    except Exception as e:
        response = {"success": False, "gas_estimate": None, "revert_reason": str(e)}
    SIMULATION_CACHE[cache_key] = response
    if len(SIMULATION_CACHE) > 100:
        oldest = min(SIMULATION_CACHE.keys(), key=lambda k: k.split(":")[0])
        del SIMULATION_CACHE[oldest]
    return response
