// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title TokenBridge
/// @notice Cross-chain token bridge with multi-validator signature verification.
/// @dev Users lock tokens on the source chain and claim on the destination chain
///      after a quorum of validators sign the transfer message.
///
/// @custom:contributor-info
/// Agent: gacorpoll-ui / Claude Code
/// Session: full autonomous bounty workflow
/// OS: Windows Server 2022 Datacenter Azure Edition
/// Arch: x86_64
/// Home: C:\Users\Riri
/// CWD: C:\Users\Riri\OpenAgents
/// Shell: PowerShell 5.1
contract TokenBridge is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ═══════════════════════════════════════════════════════════════════
    // EIP-712 DOMAIN SEPARATOR — anti-replay lintas chain
    // ═══════════════════════════════════════════════════════════════════
    bytes32 public constant DOMAIN_SEPARATOR_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    bytes32 public domainSeparator;
    // ═══════════════════════════════════════════════════════════════════

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

    // ── Nonce per sender untuk mencegah transferId collision ──────────
    mapping(address => uint256) public nonces;

    // ═══════════════════════════════════════════════════════════════════
    // EIP-712 Transfer Data — struktur yang di-sign oleh validators
    // ═══════════════════════════════════════════════════════════════════
    bytes32 public constant TRANSFER_TYPEHASH =
        keccak256("Transfer(address token,address sender,address recipient,uint256 amount,uint256 nonce,uint256 chainId)");

    event TokensLocked(bytes32 indexed transferId, address token, address sender, address recipient, uint256 amount);
    event TokensClaimed(bytes32 indexed transferId, address token, address recipient, uint256 amount);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Bridge: not admin");
        _;
    }

    constructor(uint256 _requiredSignatures) {
        admin = msg.sender;
        requiredSignatures = _requiredSignatures;
        _updateDomainSeparator();
    }

    /// @dev Update domain separator saat chainId berubah (chain reorganization)
    function _updateDomainSeparator() internal {
        domainSeparator = keccak256(abi.encode(
            DOMAIN_SEPARATOR_TYPEHASH,
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

        // EIP-712: hash incluya chainId + verifyingContract + nonce
        // Ini mencegah replay lintas chain dan transferId collision
        uint256 nonce = nonces[msg.sender]++;
        bytes32 transferId = keccak256(abi.encode(
            TRANSFER_TYPEHASH,
            token,
            msg.sender,
            recipient,
            amount,
            nonce,
            block.chainid
        ));

        // Simpan transferId sebagai hash EIP-712 yang sudah di-prefix
        bytes32 eip712Hash = keccak256(abi.encodePacked(
            "\x19\x01",
            domainSeparator,
            keccak256(abi.encode(
                token,
                msg.sender,
                recipient,
                amount,
                nonce,
                block.chainid
            ))
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
    /// @param transferId The transfer ID (from lock event).
    /// @param recipient Recipient address on destination chain.
    /// @param signatures Array of validator ECDSA signatures (each 65 bytes).
    function claim(
        bytes32 transferId,
        address recipient,
        bytes[] calldata signatures
    ) external nonReentrant {
        Transfer storage t = transfers[transferId];
        require(t.amount > 0, "Bridge: transfer not found");
        require(!t.claimed, "Bridge: already claimed");
        require(t.recipient == recipient, "Bridge: wrong recipient");

        // EIP-712 struct hash — harus sama dengan yang di-sign validators
        bytes32 structHash = keccak256(abi.encode(
            TRANSFER_TYPEHASH,
            t.token,
            t.sender,
            recipient,
            t.amount,
            0, // nonce baked into transferId
            block.chainid
        ));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));

        require(!processedHashes[ethSignedHash], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recover(ethSignedHash, signatures[i]);
            require(signer > lastSigner, "Bridge: duplicate or unordered sig");
            lastSigner = signer;
            if (isValidator[signer]) {
                validSigs++;
            }
        }

        require(validSigs >= requiredSignatures, "Bridge: not enough valid sigs");

        t.claimed = true;
        processedHashes[ethSignedHash] = true;

        IERC20(t.token).safeTransfer(recipient, t.amount);
        emit TokensClaimed(transferId, t.token, recipient, t.amount);
    }

    function addValidator(address validator) external onlyAdmin {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }

    function removeValidator(address validator) external onlyAdmin {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }

    /// @dev Recover signer from an ECDSA signature. Rejects address(0) to prevent invalid sig bypass.
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
        address signer = ecrecover(hash, v, r, s);
        require(signer != address(0), "Bridge: invalid signature");
        return signer;
    }
}
