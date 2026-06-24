// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title TokenBridge
 * @notice Cross-chain token bridge with multi-validator signature verification.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-24
 * @fixes #152 — Added tokenMapping for cross-chain token address validation
 */

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
    mapping(address => bool) public isValidator;
    mapping(bytes32 => Transfer) public transfers;
    mapping(bytes32 => bool) public processedHashes;

    // Token mapping: local address -> remote address (cross-chain validation)
    mapping(address => mapping(uint256 => address)) public tokenMapping;
    mapping(uint256 => mapping(address => address)) public remoteToLocal;

    event TokensLocked(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount);
    event TokensClaimed(bytes32 indexed transferId, address token, address recipient, uint256 amount);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    event TokenMappingAdded(address indexed localToken, uint256 indexed remoteChainId, address indexed remoteToken);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Bridge: not admin");
        _;
    }

    constructor(uint256 _requiredSignatures) {
        admin = msg.sender;
        requiredSignatures = _requiredSignatures;
    }

    /**
     * @notice Add a token mapping for cross-chain validation.
     */
    function addTokenMapping(address localToken, uint256 remoteChainId, address remoteToken) external onlyAdmin {
        require(localToken != address(0), "Bridge: zero local token");
        require(remoteToken != address(0), "Bridge: zero remote token");
        require(tokenMapping[localToken][remoteChainId] == address(0), "Bridge: mapping exists");

        tokenMapping[localToken][remoteChainId] = remoteToken;
        remoteToLocal[remoteChainId][remoteToken] = localToken;
        emit TokenMappingAdded(localToken, remoteChainId, remoteToken);
    }

    /**
     * @notice Lock tokens on the source chain to initiate a cross-chain transfer.
     */
    function lock(address token, address recipient, uint256 amount) external nonReentrant {
        require(amount > 0, "Bridge: zero amount");

        bytes32 transferId = keccak256(abi.encodePacked(token, msg.sender, recipient, amount, block.chainid, block.number));

        // Validate token is mapped if mappings exist
        address remoteToken = tokenMapping[token][block.chainid];
        if (remoteToken != address(0)) {
            require(token == remoteToken, "Bridge: unmapped token");
        }

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

    function claim(
        address token,
        address recipient,
        uint256 amount,
        bytes[] calldata signatures
    ) external nonReentrant {
        bytes32 messageHash = keccak256(abi.encodePacked(token, recipient, amount, block.chainid));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));

        require(!processedHashes[messageHash], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recover(ethSignedHash, signatures[i]);
            require(signer != address(0), "Bridge: invalid sig");
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
