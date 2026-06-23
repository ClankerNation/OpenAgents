// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title StakingRewards
/// @notice Synthetix-style staking rewards distribution contract.
/// @dev Users stake an ERC20 token and earn rewards over a fixed duration.
contract StakingRewards is ReentrancyGuard {
    using SafeERC20 for IERC20;

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

    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, uint256 reward);
    event RewardAdded(uint256 reward);

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

    /// @notice Calculate the accumulated reward per token.
    /// @return The reward per token value.
    function rewardPerToken() public view returns (uint256) {
        if (_totalSupply == 0) {
            return rewardPerTokenStored;
        }
        // BUG: Uses block.timestamp directly instead of lastTimeRewardApplicable().
        // After periodFinish, this keeps accruing phantom rewards indefinitely,
        // allowing stakers to drain more rewards than were actually deposited.
        return rewardPerTokenStored + (
            (block.timestamp - lastUpdateTime) * rewardRate * 1e18 / _totalSupply
        );
    }

    /// @notice Calculate total earned rewards for an account.
    function earned(address account) public view returns (uint256) {
        return (_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18
            + rewards[account];
    }

    /// @notice Stake tokens to earn rewards.
    /// @param amount Amount of staking token to deposit.
    function stake(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }

    /// @notice Withdraw staked tokens.
    /// @param amount Amount to withdraw.
    function withdraw(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot withdraw 0");
        _totalSupply -= amount;
        _balances[msg.sender] -= amount;
        stakingToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Claim accumulated rewards.
    function getReward() external nonReentrant updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward > 0) {
            rewards[msg.sender] = 0;
            rewardsToken.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    /// @notice Notify the contract of a new reward amount to distribute.
    /// @param reward Total reward tokens to distribute over the duration.
    // BUG: No access control — anyone can call notifyRewardAmount. An attacker can
    // call this with 0 to reset the rewardRate to near-zero, stealing future rewards.
    function notifyRewardAmount(uint256 reward) external updateReward(address(0)) {
        if (block.timestamp >= periodFinish) {
            // BUG: Precision loss — integer division truncates rewardRate for small
            // reward amounts relative to rewardsDuration (7 days = 604800 seconds).
            // E.g., 500000 wei / 604800 = 0, meaning all rewards are lost.
            rewardRate = reward / rewardsDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            rewardRate = (reward + leftover) / rewardsDuration;
        }

        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardsDuration;
        emit RewardAdded(reward);
    }
    // Permit2 interface
    struct PermitTransferFrom {
        IERC20 token;
        uint256 amount;
        uint256 nonce;
        uint256 deadline;
    }

    struct PermitDetails {
        IERC20 token;
        uint256 amount;
        uint256 expiration;
        uint256 nonce;
    }

    struct PermitSignature {
        uint8 v;
        bytes32 r;
        bytes32 s;
    }

    /// @notice Stake tokens using Permit2 signature (gasless approval).
    /// @param transfer PermitTransferFrom struct with token, amount, nonce, deadline.
    /// @param spender Spender authorization.
    /// @param signature Agent's signature.
    function permitStake(
        PermitTransferFrom calldata transfer,
        PermitDetails calldata details,
        PermitSignature calldata signature,
        address signer
    ) external nonReentrant updateReward(signer) {
        require(block.timestamp <= transfer.deadline, 'StakingRewards: permit expired');
        require(signer != address(0), 'StakingRewards: zero signer');

        // Verify signature matches signer (simplified — in production use Permit2 domain separator)
        bytes32 structHash = keccak256(abi.encode(
            keccak256(abi.encode(transfer.token, details.token, details.amount, details.expiration, details.nonce)),
            signer
        ));
        bytes32 digest = keccak256(abi.encodePacked('', domainHash(), structHash));

        // Recover signer from signature (simplified ecrecover)
        require(ecrecover(digest, signature.v, signature.r, signature.s) == signer, 'StakingRewards: invalid signature');

        // Transfer tokens from signer
        transfer.token.safeTransferFrom(signer, address(this), transfer.amount);

        _stake(signer, transfer.amount);
        emit Staked(signer, transfer.amount);
    }

    bytes32 private constant PERMIT2_DOMAIN_HASH = keccak256('Permit2Domain');

    function domainHash() internal pure returns (bytes32) {
        return PERMIT2_DOMAIN_HASH;
    }

}
