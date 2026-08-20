// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title TokenBridge
/// @notice Cross-chain token bridge with multi-validator signature verification and token mapping.
/// @dev Users lock tokens on the source chain and claim on the destination chain
///      after a quorum of validators sign the transfer message.
contract TokenBridge is ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct Transfer {
        address token;
        address sender;
        address recipient;
        uint256 amount;
        bool claimed;
    }

    address public admin;
    uint256 public requiredSignatures;
    uint256 public nonce; // Unique nonce to prevent transfer ID collisions
    mapping(address => bool) public isValidator;
    mapping(bytes32 => Transfer) public transfers;
    mapping(bytes32 => bool) public processedHashes;
    
    // Token mapping: local token address -> remote token address
    mapping(address => address) public tokenMapping;

    event TokensLocked(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount);
    event TokensClaimed(bytes32 indexed transferId, address token, address recipient, uint256 amount);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    event TokenMappingAdded(address indexed localToken, address indexed remoteToken);
    event TokenMappingRemoved(address indexed localToken);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Bridge: not admin");
        _;
    }

    constructor(uint256 _requiredSignatures) {
        admin = msg.sender;
        requiredSignatures = _requiredSignatures;
    }

    /// @notice Add or update a token mapping between local and remote chains.
    /// @param localToken Token address on this chain.
    /// @param remoteToken Corresponding token address on the remote chain.
    function addTokenMapping(address localToken, address remoteToken) external onlyAdmin {
        require(localToken != address(0), "Bridge: zero local token");
        require(remoteToken != address(0), "Bridge: zero remote token");
        tokenMapping[localToken] = remoteToken;
        emit TokenMappingAdded(localToken, remoteToken);
    }

    /// @notice Remove a token mapping.
    /// @param localToken Token address on this chain to unmapped.
    function removeTokenMapping(address localToken) external onlyAdmin {
        delete tokenMapping[localToken];
        emit TokenMappingRemoved(localToken);
    }

    /// @notice Lock tokens on the source chain to initiate a cross-chain transfer.
    /// @param token ERC20 token address (must be mapped).
    /// @param recipient Destination address on the target chain.
    /// @param amount Amount of tokens to bridge.
    function lock(address token, address recipient, uint256 amount) external nonReentrant {
        require(amount > 0, "Bridge: zero amount");
        
        // Validate token is in the mapping
        address remoteToken = tokenMapping[token];
        require(remoteToken != address(0), "Bridge: token not mapped");

        // Include chainid, nonce and remote token in hash to prevent replay/collision
        bytes32 transferId = keccak256(abi.encodePacked(
            block.chainid,
            nonce++,
            token,
            remoteToken,
            msg.sender,
            recipient,
            amount
        ));

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        transfers[transferId] = Transfer({
            token: token,
            sender: msg.sender,
            recipient: recipient,
            amount: amount,
            claimed: false
        });

        emit TokensLocked(transferId, token, msg.sender, recipient, amount);
    }

    /// @notice Claim bridged tokens on the destination chain with validator signatures.
    /// @param token Token address on this chain.
    /// @param recipient Recipient address.
    /// @param amount Amount to claim.
    /// @param signatures Array of validator ECDSA signatures (each 65 bytes).
    function claim(
        address token,
        address recipient,
        uint256 amount,
        bytes[] calldata signatures
    ) external nonReentrant {
        bytes32 messageHash = keccak256(abi.encodePacked(token, recipient, amount));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));

        require(!processedHashes[messageHash], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recover(ethSignedHash, signatures[i]);
            require(signer != address(0), "Bridge: invalid signature");
            require(signer > lastSigner, "Bridge: duplicate or unordered sig");
            lastSigner = signer;
            if (isValidator[signer]) {
                validSigs++;
            }
        }

        require(validSigs >= requiredSignatures, "Bridge: not enough valid sigs");
        processedHashes[messageHash] = true;

        IERC20(token).safeTransfer(recipient, amount);
        emit TokensClaimed(messageHash, token, recipient, amount);
    }

    function addValidator(address validator) external onlyAdmin {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }

    function removeValidator(address validator) external onlyAdmin {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }

    /// @dev Recover signer from an ECDSA signature.
    function _recover(bytes32 hash, bytes memory sig) internal pure returns (address) {
        require(sig.length == 65, "Bridge: invalid sig length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        return ecrecover(hash, v, r, s);
    }
}
