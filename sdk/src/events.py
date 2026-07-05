"""Event subscription and decoding for OpenAgents SDK."""
from web3 import Web3
import asyncio

class EventSubscriber:
    def __init__(self, w3: Web3, contract_address: str, abi: list):
        self.w3 = w3
        self.contract = w3.eth.contract(address=contract_address, abi=abi)
    
    async def subscribe(self, event_name: str, callback, from_block="latest"):
        """Subscribe to contract events."""
        event = getattr(self.contract.events, event_name)
        event_filter = event.create_filter(fromBlock=from_block)
        while True:
            for log in event_filter.get_new_entries():
                await callback(self._decode(log))
            await asyncio.sleep(2)
    
    def _decode(self, log) -> dict:
        """Decode event log."""
        return {
            "event": log["event"],
            "args": dict(log["args"]),
            "block": log["blockNumber"],
            "tx": log["transactionHash"].hex(),
        }
