import asyncio
from typing import Optional, Dict, Any
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

class TransactionSimulator:
    """Simulate transactions before sending to estimate success probability."""
    
    def __init__(self, rpc_url: str = "https://api.mainnet-beta.solana.com"):
        self.client = AsyncClient(rpc_url)
    
    async def simulate(self, tx_data: bytes, accounts: Optional[list] = None) -> Dict[str, Any]:
        """Simulate a transaction and return the result."""
        resp = await self.client.simulate_transaction(tx_data, sig_verify=False, commitment=Confirmed)
        result = resp.get("result", {})
        if result.get("err"):
            return {"success": False, "error": str(result["err"]), "logs": result.get("logs", [])}
        return {"success": True, "logs": result.get("logs", []), "units_consumed": result.get("units_consumed", 0)}
    
    async def estimate_success(self, tx_data: bytes) -> float:
        """Return success probability 0.0-1.0."""
        result = await self.simulate(tx_data)
        if result["success"]:
            return 0.95
        return 0.1
    
    async def close(self):
        await self.client.close()
