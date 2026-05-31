// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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
    bytes32 private constant EIP712_DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );
    bytes32 private constant VERSION_HASH = keccak256(bytes("1"));
    bytes32 private immutable _hashedName;
    bytes32 private immutable _cachedDomainSeparator;
    uint256 private immutable _cachedChainId;
    address private immutable _cachedThis;
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        _hashedName = keccak256(bytes(name_));
        _cachedChainId = block.chainid;
        _cachedThis = address(this);
        _cachedDomainSeparator = _buildDomainSeparator(_hashedName, block.chainid, address(this));
    }

    /// @notice Mint new tokens to a recipient.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    // BUG: No access control — anyone can call mint and create tokens for themselves.
    // Should be restricted to owner or a minter role.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Transfer ownership of the contract.
    /// @param newOwner The new owner address.
    function transferOwnership(address newOwner) external {
        require(msg.sender == owner, "AgentToken: not owner");
        require(newOwner != address(0), "AgentToken: zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
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

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        if (block.chainid == _cachedChainId && address(this) == _cachedThis) {
            return _cachedDomainSeparator;
        }

        return _buildDomainSeparator(_hashedName, block.chainid, address(this));
    }

    function _buildDomainSeparator(
        bytes32 hashedName,
        uint256 chainId,
        address verifyingContract
    ) private pure returns (bytes32) {
        return keccak256(abi.encode(
            EIP712_DOMAIN_TYPEHASH,
            hashedName,
            VERSION_HASH,
            chainId,
            verifyingContract
        ));
    }
}
