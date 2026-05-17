// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @contributor Metatron
/// @platform Hermes Agent v4 (cron job), running on WSL2 (Ubuntu) x86_64
/// @runtime OS: Linux (WSL2), arch: x86_64, cwd: /home/power/projects/OpenAgents, shell: bash
/// @date 2026-05-17T00:21:00Z

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, and EIP-2612 permit functionality.
/// @dev Used as the native token for the OpenAgents platform.
contract AgentToken is ERC20, ERC20Burnable {
    address public owner;

    /// @notice Maximum total supply of tokens — prevents unbounded inflation.
    uint256 public immutable MAX_SUPPLY;

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
    );
    bytes32 public immutable DOMAIN_SEPARATOR;
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply,
        uint256 maxSupply_
    ) ERC20(name_, symbol_) {
        require(maxSupply_ >= initialSupply, "AgentToken: max supply below initial");
        owner = msg.sender;
        MAX_SUPPLY = maxSupply_;
        _mint(msg.sender, initialSupply);
        DOMAIN_SEPARATOR = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Mint new tokens to a recipient. Only callable by the owner.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "AgentToken: not owner");
        require(totalSupply() + amount <= MAX_SUPPLY, "AgentToken: exceeds max supply");
        _mint(to, amount);
    }

    /// @notice Burn tokens from the caller's balance. Inherited from ERC20Burnable.
    /// @dev Calls ERC20Burnable.burn(uint256) — reduces caller's balance and totalSupply.
    /// @param amount Amount of tokens to burn.
    function burn(uint256 amount) public override {
        _burn(msg.sender, amount);
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
        require(block.timestamp <= deadline, "AgentToken: permit expired");

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
}
