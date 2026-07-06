// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

/// @title TokenBridge
/// @notice Cross-chain token bridge with multi-validator EIP-712 signature verification.
/// @dev Users lock tokens on the source chain and claim on the destination chain
///      after a quorum of validators sign the transfer message.
///      EIP-712 typed data prevents cross-chain replay attacks by including
///      chainId, verifyingContract, and a per-sender nonce.
///
/// @custom:contributor-info
///   author: EVM0x
///   github: https://github.com/EVM0x
///   os: Linux (6.8.0-117-generic)
///   arch: x86_64
///   home: /home/ubuntu
///   workdir: /home/ubuntu/openagents-fix
///   shell: /bin/bash
contract TokenBridge is ReentrancyGuard, EIP712 {
    using SafeERC20 for IERC20;

    // EIP-712 type hash for the Transfer message
    bytes32 private constant TRANSFER_TYPEHASH = keccak256(
        "Transfer(address token,address sender,address recipient,uint256 amount,uint256 nonce)"
    );

    struct Transfer {
        address token;
        address sender;
        address recipient;
        uint256 amount;
        bool claimed;
    }

    address public admin;
    uint256 public requiredSignatures;
    mapping(address => bool) public isValidator;
    mapping(bytes32 => Transfer) public transfers;
    mapping(bytes32 => bool) public processedHashes;
    mapping(address => uint256) public nonces;

    event TokensLocked(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount, uint256 nonce);
    event TokensClaimed(bytes32 indexed transferId, address token, address recipient, uint256 amount);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Bridge: not admin");
        _;
    }

    /// @param _requiredSignatures Minimum number of validator signatures required.
    constructor(uint256 _requiredSignatures) EIP712("TokenBridge", "1") {
        admin = msg.sender;
        requiredSignatures = _requiredSignatures;
    }

    /// @notice Lock tokens on the source chain to initiate a cross-chain transfer.
    /// @param token ERC20 token address.
    /// @param recipient Destination address on the target chain.
    /// @param amount Amount of tokens to bridge.
    function lock(address token, address recipient, uint256 amount) external nonReentrant {
        require(amount > 0, "Bridge: zero amount");

        uint256 nonce = nonces[msg.sender]++;
        // Include chainId + contract address + nonce to prevent cross-chain replay
        // and transferId collision for repeated transfers.
        bytes32 transferId = keccak256(
            abi.encode(block.chainid, address(this), token, msg.sender, recipient, amount, nonce)
        );

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        transfers[transferId] = Transfer({
            token: token,
            sender: msg.sender,
            recipient: recipient,
            amount: amount,
            claimed: false
        });

        emit TokensLocked(transferId, token, msg.sender, recipient, amount, nonce);
    }

    /// @notice Claim bridged tokens on the destination chain with validator signatures.
    /// @param token Token address.
    /// @param sender Original sender address from the source chain.
    /// @param recipient Recipient address.
    /// @param amount Amount to claim.
    /// @param nonce Sender's nonce used when locking.
    /// @param signatures Array of validator ECDSA signatures (each 65 bytes).
    function claim(
        address token,
        address sender,
        address recipient,
        uint256 amount,
        uint256 nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        // Build the EIP-712 typed data hash — includes domain separator
        // which embeds chainId + verifyingContract, preventing cross-chain replay.
        bytes32 structHash = keccak256(
            abi.encode(TRANSFER_TYPEHASH, token, sender, recipient, amount, nonce)
        );
        bytes32 digest = _hashTypedDataV4(structHash);

        require(!processedHashes[digest], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = ECDSA.recover(digest, signatures[i]);
            // Reject zero-address from invalid ecrecover
            require(signer != address(0), "Bridge: invalid signature");
            require(signer > lastSigner, "Bridge: duplicate or unordered sig");
            lastSigner = signer;
            if (isValidator[signer]) {
                validSigs++;
            }
        }

        require(validSigs >= requiredSignatures, "Bridge: not enough valid sigs");
        processedHashes[digest] = true;

        IERC20(token).safeTransfer(recipient, amount);
        emit TokensClaimed(digest, token, recipient, amount);
    }

    function addValidator(address validator) external onlyAdmin {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }

    function removeValidator(address validator) external onlyAdmin {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }

    /// @notice Return the EIP-712 domain separator for off-chain signature construction.
    function DOMAIN_SEPARATOR() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
