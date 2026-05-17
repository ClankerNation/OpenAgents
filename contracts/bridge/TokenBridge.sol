// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

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
    uint256 public nonce;
    mapping(address => bool) public isValidator;
    mapping(bytes32 => Transfer) public transfers;
    mapping(bytes32 => bool) public processedHashes;
    mapping(address => uint256) public senderNonces;

    bytes32 public constant EIP712_DOMAIN_TYPEHASH = keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant CLAIM_TYPEHASH = keccak256("Claim(address token,address recipient,uint256 amount,uint256 nonce)");
    bytes32 public domainSeparator;

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
        domainSeparator = keccak256(abi.encode(
            EIP712_DOMAIN_TYPEHASH,
            keccak256("TokenBridge"),
            keccak256("1"),
            block.chainid,
            address(this)
        ));
    }

    function lock(address token, address recipient, uint256 amount) external nonReentrant {
        require(amount > 0, "Bridge: zero amount");

        nonce++;
        bytes32 transferId = keccak256(abi.encodePacked(
            token, msg.sender, recipient, amount, block.chainid, address(this), nonce
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

    function claim(
        address token,
        address recipient,
        uint256 amount,
        uint256 _nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        bytes32 claimHash = keccak256(abi.encode(
            CLAIM_TYPEHASH,
            token,
            recipient,
            amount,
            _nonce
        ));
        bytes32 digest = keccak256(abi.encodePacked(
            "\x19\x01", domainSeparator, claimHash
        ));

        require(!processedHashes[digest], "Bridge: already processed");
        require(signatures.length >= requiredSignatures, "Bridge: insufficient sigs");

        uint256 validSigs = 0;
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recover(digest, signatures[i]);
            require(signer != address(0), "Bridge: invalid sig");
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
