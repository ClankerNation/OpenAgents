// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title GasSponsorshipRelay
 * @notice Allows autonomous AI agents to execute transactions with sponsored gas under strict cryptographic verification.
 */
contract GasSponsorshipRelay is EIP712, Ownable, ReentrancyGuard {
    using ECDSA for bytes32;

    bytes32 public constant RELAY_TYPEHASH = keccak256(
        "RelayedTransaction(address agent,address target,bytes data,uint256 nonce,uint256 deadline)"
    );

    mapping(address => uint256) public nonces;
    mapping(address => bool) public authorizedPaymasters;

    event TransactionRelayed(address indexed agent, address indexed target, uint256 nonce, bool success);
    event PaymasterUpdated(address indexed paymaster, bool status);

    constructor() EIP712("OpenAgentsGasRelay", "1.0") Ownable(msg.sender) {
        authorizedPaymasters[msg.sender] = true;
    }

    modifier onlyPaymaster() {
        require(authorizedPaymasters[msg.sender], "GasRelay: caller is not authorized paymaster");
        _;
    }

    function setPaymaster(address paymaster, bool status) external onlyOwner {
        authorizedPaymasters[paymaster] = status;
        emit PaymasterUpdated(paymaster, status);
    }

    function executeRelayed(
        address agent,
        address target,
        bytes calldata data,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant onlyPaymaster returns (bytes memory) {
        require(block.timestamp <= deadline, "GasRelay: transaction expired");
        require(target != address(0), "GasRelay: invalid target");

        uint256 currentNonce = nonces[agent]++;
        
        bytes32 structHash = keccak256(
            abi.encode(RELAY_TYPEHASH, agent, target, keccak256(data), currentNonce, deadline)
        );
        bytes32 hash = _hashTypedDataV4(structHash);
        
        address signer = hash.recover(signature);
        require(signer == agent, "GasRelay: invalid signature");

        (bool success, bytes memory result) = target.call(data);
        require(success, "GasRelay: target execution failed");

        emit TransactionRelayed(agent, target, currentNonce, success);
        return result;
    }
}
