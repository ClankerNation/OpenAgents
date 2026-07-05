"""Contract deployment helpers for OpenAgents SDK."""
from web3 import Web3
import json

class ContractDeployer:
    def __init__(self, w3: Web3, private_key: str):
        self.w3 = w3
        self.account = w3.eth.account.from_key(private_key)
    
    def deploy(self, abi: list, bytecode: str, *args) -> dict:
        """Deploy contract with constructor args."""
        contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        tx = contract.constructor(*args).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 3000000,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return {"address": receipt.contractAddress, "tx_hash": tx_hash.hex(), "gas": receipt.gasUsed}
    
    def verify(self, address: str) -> bool:
        """Verify deployed contract has code."""
        return len(self.w3.eth.get_code(address)) > 0
