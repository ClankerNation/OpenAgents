// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title GasRelay
/// @notice Meta-transaction relay for agent operations — enables gasless transactions.
/// @dev Users sign typed data off-chain; a relayer submits the tx and pays gas.
///      The relay verifies EIP-712 signatures and forwards calls to target contracts.
contract GasRelay is EIP712, ReentrancyGuard {
    using ECDSA for bytes32;

    // Authorized relayers who can submit meta-tx on behalf of users
    mapping(address => bool) public relayers;
    address public owner;

    // Replay protection: signer => nonce
    mapping(address => uint256) public nonces;

    // Typehash for the ForwardRequest struct
    bytes32 private constant FORWARD_REQUEST_TYPEHASH =
        keccak256("ForwardRequest(address from,address to,uint256 value,bytes data,uint256 nonce,uint256 deadline)");

    event RelayerAuthorized(address indexed relayer, bool authorized);
    event MetaTransactionExecuted(
        address indexed from,
        address indexed to,
        bytes data,
        uint256 nonce
    );

    struct ForwardRequest {
        address from;    // The actual sender (signer)
        address to;      // Target contract
        uint256 value;   // ETH value to forward
        bytes data;      // Calldata
        uint256 nonce;   // Replay protection
        uint256 deadline; // Expiration timestamp
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "GasRelay: not owner");
        _;
    }

    constructor(address _owner)
        EIP712("GasRelay", "1")
    {
        owner = _owner;
    }

    /// @notice Authorize or deauthorize a relayer address.
    function setRelayer(address relayer, bool authorized) external onlyOwner {
        relayers[relayer] = authorized;
        emit RelayerAuthorized(relayer, authorized);
    }

    /// @notice Execute a meta-transaction on behalf of a user.
    /// @param req The forward request containing user's intent.
    /// @param signature EIP-712 signature from the user (req.from).
    function executeMetaTransaction(
        ForwardRequest calldata req,
        bytes calldata signature
    ) external payable nonReentrant returns (bytes memory) {
        require(relayers[msg.sender], "GasRelay: not authorized relayer");
        require(block.timestamp <= req.deadline, "GasRelay: request expired");
        require(req.from != address(0), "GasRelay: invalid sender");

        // Verify nonce matches to prevent replay
        require(req.nonce == nonces[req.from], "GasRelay: invalid nonce");

        // Verify EIP-712 signature
        bytes32 digest = _hashTypedDataV4(
            keccak256(
                abi.encode(
                    FORWARD_REQUEST_TYPEHASH,
                    req.from,
                    req.to,
                    req.value,
                    keccak256(req.data),
                    req.nonce,
                    req.deadline
                )
            )
        );

        address signer = digest.recover(signature);
        require(signer == req.from, "GasRelay: invalid signature");

        // Increment nonce (replay protection)
        nonces[req.from]++;

        // Forward the call to the target contract
        (bool success, bytes memory result) = req.to.call{value: req.value}(req.data);
        require(success, "GasRelay: forwarded call failed");

        emit MetaTransactionExecuted(req.from, req.to, req.data, req.nonce);
        return result;
    }

    /// @notice Get the current nonce for a signer.
    function getNonce(address signer) external view returns (uint256) {
        return nonces[signer];
    }

    receive() external payable {}
}
