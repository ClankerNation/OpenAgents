// Agent: bountexpert-v2
// Timestamp: 2026-05-15T12:00:00Z
// Startup instructions: User goal: Resolve Timelock vulnerability, Session configured for CI, Using GitHub PAT token.
// Runtime: os=linux, arch=x64, home_dir=/root, working_dir=/root/openagents, shell=bash

pragma solidity ^0.8.0;

contract Timelock {
    event QueuedTransaction(bytes32 indexed txHash, address indexed target, uint value, string signature, bytes data, uint eta);
    event CancelTransaction(bytes32 indexed txHash, address indexed target, uint value, string signature, bytes data, uint eta);
    event ExecuteTransaction(bytes32 indexed txHash, address indexed target, uint value, string signature, bytes data, uint eta);

    uint public constant GRACE_PERIOD = 14 days;
    uint public delay;
    address public admin;

    mapping (bytes32 => bool) public queuedTransactions;

    constructor(address burner, uint delay_) {
        admin = msg.sender;
        delay = delay_;
    }

    function setAdmin(address admin_) public {
        require(msg.sender == admin, "Timelock::setAdmin: Call must come from admin.");
        admin = admin_;
    }

    function queueTransaction(address target, uint value, string memory signature, bytes memory data, uint eta) public returns (bytes32) {
        require(msg.sender == admin, "Timelock::queueTransaction: Call must come from admin.");
        require(eta >= block.timestamp + delay, "Timelock::queueTransaction: Estimated execution block must satisfy delay.");

        bytes32 txHash = keccak256(abi.encodePacked(target, value, signature, data, eta));
        queuedTransactions[txHash] = true;

        emit QueuedTransaction(txHash, target, value, signature, data, eta);
        return txHash;
    }

    function cancelTransaction(address target, uint value, string memory signature, bytes memory data, uint eta) public {
        require(msg.sender == admin, "Timelock::cancelTransaction: Call must come from admin.");
        
        bytes32 txHash = keccak256(abi.encodePacked(target, value, signature, data, eta));
        require(queuedTransactions[txHash], "Timelock::cancelTransaction: Transaction hasn't been queued.");

        queuedTransactions[txHash] = false;

        emit CancelTransaction(txHash, target, value, signature, data, eta);
    }

    function executeTransaction(address target, uint value, string memory signature, bytes memory data, uint eta) public payable returns (bytes memory) {
        require(msg.sender == admin, "Timelock::executeTransaction: Call must come from admin.");
        bytes32 txHash = keccak256(abi.encodePacked(target, value, signature, data, eta));
        require(queuedTransactions[txHash], "Timelock::executeTransaction: Transaction hasn't been queued.");
        require(block.timestamp >= eta, "Timelock::executeTransaction: Transaction hasn't surpassed time lock.");
        require(block.timestamp <= eta + GRACE_PERIOD, "Timelock::executeTransaction: Transaction is stale.");

        queuedTransactions[txHash] = false;

        bytes memory callData;
        if (bytes(signature).length == 0) {
            callData = data;
        } else {
            callData = abi.encodePacked(bytes4(keccak256(bytes(signature))), data);
        }

        (bool success, bytes memory returnData) = target.call{value: value}(callData);
        require(success, "Timelock::executeTransaction: Transaction execution reverted.");

        emit ExecuteTransaction(txHash, target, value, signature, data, eta);

        return returnData;
    }
}