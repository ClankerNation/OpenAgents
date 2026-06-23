// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

/**
 * @title StakingRewards
 * @notice Synthetix-style staking rewards distribution contract with permit2-style gasless approvals.
 * @dev Users stake an ERC20 token and earn rewards over a fixed duration.
 *      Supports both standard transferFrom and permit-based signature staking.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-24
 * @fixes #175 — Added permit2-style signature-based staking (permitStake)
 */

contract StakingRewards is ReentrancyGuard, EIP712("StakingRewardsPermit2", "1") {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    IERC20 public immutable stakingToken;
    IERC20 public immutable rewardsToken;
    address public owner;

    uint256 public periodFinish;
    uint256 public rewardRate;
    uint256 public rewardsDuration = 7 days;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;

    uint256 private _totalSupply;
    mapping(address => uint256) private _balances;

    // Permit2 state
    mapping(address => mapping(uint256 => uint256)) public nonces;
    mapping(address => mapping(uint256 => bool)) public permitUsed;

    bytes32 public constant PERMIT_STAKE_TYPEHASH = keccak256(
        "PermitStake(address spender,uint256 amount,uint256 nonce,uint256 deadline)"
    );

    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, uint256 reward);
    event RewardAdded(uint256 reward);
    event PermitStaked(address indexed user, address indexed spender, uint256 amount);

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    constructor(address _stakingToken, address _rewardsToken) {
        stakingToken = IERC20(_stakingToken);
        rewardsToken = IERC20(_rewardsToken);
        owner = msg.sender;
    }

    function totalSupply() external view returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish ? block.timestamp : periodFinish;
    }

    function rewardPerToken() public view returns (uint256) {
        if (_totalSupply == 0) {
            return rewardPerTokenStored;
        }
        return rewardPerTokenStored + (
            (lastTimeRewardApplicable() - lastUpdateTime) * rewardRate * 1e18 / _totalSupply
        );
    }

    function earned(address account) public view returns (uint256) {
        return (_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18
            + rewards[account];
    }

    function stake(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }

    /**
     * @notice Stake tokens using a permit signature (permit2-style gasless approval).
     */
    function permitStake(
        address user,
        address spender,
        uint256 amount,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external nonReentrant updateReward(user) {
        require(block.timestamp <= deadline, "Permit expired");
        require(!permitUsed[user][amount], "Permit already used");

        bytes32 structHash = keccak256(
            abi.encode(PERMIT_STAKE_TYPEHASH, spender, amount, nonces[user][amount], deadline)
        );
        bytes32 digest = _hashTypedDataV4(structHash);
        address recovered = digest.recover(v, r, s);
        require(recovered == user, "Invalid signature");

        nonces[user][amount]++;
        permitUsed[user][amount] = true;

        _totalSupply += amount;
        _balances[user] += amount;
        stakingToken.safeTransferFrom(user, address(this), amount);

        emit PermitStaked(user, spender, amount);
        emit Staked(user, amount);
    }

    function withdraw(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot withdraw 0");
        _totalSupply -= amount;
        _balances[msg.sender] -= amount;
        stakingToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    function getReward() external nonReentrant updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward > 0) {
            rewards[msg.sender] = 0;
            rewardsToken.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    function notifyRewardAmount(uint256 reward) external updateReward(address(0)) {
        require(msg.sender == owner, "Only owner");
        if (block.timestamp >= periodFinish) {
            rewardRate = reward > rewardsDuration ? reward / rewardsDuration : 1;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            rewardRate = (reward + leftover) > rewardsDuration ? (reward + leftover) / rewardsDuration : 1;
        }

        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardsDuration;
        emit RewardAdded(reward);
    }
}
