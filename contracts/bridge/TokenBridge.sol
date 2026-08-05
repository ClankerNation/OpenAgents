// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @custom:contributor-info
///   agent: Codex
///   public_task: OpenAgents issue #6, prevent TokenBridge signature replay
///   runtime: macOS Darwin arm64, zsh, /tmp/openagents-issue6.iFxUfQ/repo
///   privacy: private system/developer/session initialization text intentionally omitted

/// @title TokenBridge
/// @notice Cross-chain token bridge with multi-validator EIP-712 signature verification.
/// @dev Users lock tokens on the source chain and claim on the destination chain
///      after a quorum of validators sign the transfer message.
contract TokenBridge is ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 private constant EIP712_DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );
    bytes32 private constant BRIDGE_TRANSFER_TYPEHASH = keccak256(
        "BridgeTransfer(address token,address sender,address recipient,uint256 amount,uint256 nonce)"
    );
    bytes32 public immutable DOMAIN_SEPARATOR;

    struct Transfer {
        address token;
        address sender;
        address recipient;
        uint256 amount;
        uint256 nonce;
        bool claimed;
    }

    address public admin;
    uint256 public requiredSignatures;
    mapping(address => bool) public isValidator;
    mapping(bytes32 => Transfer) public transfers;
    mapping(bytes32 => bool) public processedHashes;
    mapping(address => uint256) public nonces;

    event TokensLocked(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount, uint256 nonce);
    event TokensClaimed(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount, uint256 nonce);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Bridge: not admin");
        _;
    }

    constructor(uint256 _requiredSignatures) {
        admin = msg.sender;
        requiredSignatures = _requiredSignatures;
        DOMAIN_SEPARATOR = keccak256(abi.encode(
            EIP712_DOMAIN_TYPEHASH,
            keccak256(bytes("TokenBridge")),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Lock tokens on the source chain to initiate a cross-chain transfer.
    /// @param token ERC20 token address.
    /// @param recipient Destination address on the target chain.
    /// @param amount Amount of tokens to bridge.
    function lock(address token, address recipient, uint256 amount) external nonReentrant {
        require(amount > 0, "Bridge: zero amount");
        require(token != address(0), "Bridge: zero token");
        require(recipient != address(0), "Bridge: zero recipient");

        uint256 nonce = nonces[msg.sender]++;
        bytes32 transferId = getTransferDigest(token, msg.sender, recipient, amount, nonce);

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        transfers[transferId] = Transfer({
            token: token,
            sender: msg.sender,
            recipient: recipient,
            amount: amount,
            nonce: nonce,
            claimed: false
        });

        emit TokensLocked(transferId, token, msg.sender, recipient, amount, nonce);
    }

    /// @notice Claim bridged tokens on the destination chain with validator signatures.
    /// @param token Token address.
    /// @param sender Source-chain sender.
    /// @param recipient Recipient address.
    /// @param amount Amount to claim.
    /// @param nonce Source-chain sender nonce.
    /// @param signatures Array of validator ECDSA signatures (each 65 bytes).
    function claim(
        address token,
        address sender,
        address recipient,
        uint256 amount,
        uint256 nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        bytes32 transferId = getTransferDigest(token, sender, recipient, amount, nonce);

        require(!processedHashes[transferId], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recover(transferId, signatures[i]);
            require(signer != address(0), "Bridge: invalid signature");
            require(signer > lastSigner, "Bridge: duplicate or unordered sig");
            lastSigner = signer;
            if (isValidator[signer]) {
                validSigs++;
            }
        }

        require(validSigs >= requiredSignatures, "Bridge: not enough valid sigs");
        processedHashes[transferId] = true;

        IERC20(token).safeTransfer(recipient, amount);
        emit TokensClaimed(transferId, token, sender, recipient, amount, nonce);
    }

    function addValidator(address validator) external onlyAdmin {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }

    function removeValidator(address validator) external onlyAdmin {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }

    function getTransferStructHash(
        address token,
        address sender,
        address recipient,
        uint256 amount,
        uint256 nonce
    ) public pure returns (bytes32) {
        return keccak256(abi.encode(
            BRIDGE_TRANSFER_TYPEHASH,
            token,
            sender,
            recipient,
            amount,
            nonce
        ));
    }

    function getTransferDigest(
        address token,
        address sender,
        address recipient,
        uint256 amount,
        uint256 nonce
    ) public view returns (bytes32) {
        return keccak256(abi.encodePacked(
            "\x19\x01",
            DOMAIN_SEPARATOR,
            getTransferStructHash(token, sender, recipient, amount, nonce)
        ));
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
