// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]


import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, and EIP-2612 permit functionality.
/// @dev Used as the native token for the OpenAgents platform.
contract AgentToken is ERC20, ERC20Burnable {
    address public owner;
    // BUG: No max supply cap — tokens can be minted infinitely, leading to
    // unbounded inflation and devaluation of existing holders' tokens.

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
    );
    bytes32 public immutable DOMAIN_SEPARATOR;
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        DOMAIN_SEPARATOR = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Mint new tokens to a recipient.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    // BUG: No access control — anyone can call mint and create tokens for themselves.
    // Should be restricted to owner or a minter role.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }


    /// @notice EIP-2612 permit: approve via signature.
    /// @param _owner Token holder granting approval.
    /// @param spender Address to approve.
    /// @param value Amount to approve.
    /// @param deadline Timestamp after which the permit expires.
    /// @param v ECDSA recovery byte.
    /// @param r ECDSA r value.
    /// @param s ECDSA s value.
    function permit(
        address _owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        // BUG: Deadline is not checked — expired permits are still accepted, allowing
        // old signatures to be used indefinitely. Should require(block.timestamp <= deadline).
        bytes32 structHash = keccak256(abi.encode(
            PERMIT_TYPEHASH,
            _owner,
            spender,
            value,
            nonces[_owner]++,
            deadline
        ));

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }

    // --- Timelock Ownership (2-day delay) ---
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;
    uint256 public constant TIMELOCK_DELAY = 2 days;

    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner, uint256 executeAfter);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledNewOwner);
    event OwnershipAccepted(address indexed previousOwner, address indexed newOwner);

    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "New owner is zero");
        require(newOwner != owner, "Already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferInitiated(owner, newOwner, block.timestamp + TIMELOCK_DELAY);
    }

    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Not pending owner");
        require(_transferInitiatedAt > 0, "No pending transfer");
        require(block.timestamp >= _transferInitiatedAt + TIMELOCK_DELAY, "Timelock not expired");
        address oldOwner = owner;
        owner = msg.sender;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipAccepted(oldOwner, msg.sender);
    }

    function cancelTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "No pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(owner, cancelled);
    }

    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    function transferInitiatedAt() external view returns (uint256) {
        return _transferInitiatedAt;
    }

}
