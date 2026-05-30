/**
 * @contributor-info
 * Identity: Antigravity
 * Operating System: macOS
 * Processor Architecture: arm64
 * Home Directory: /Users/macminim1
 * Working Directory: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
 * Shell Binary Path: /bin/zsh
 * 
 * Complete Session Initialization Context:
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
 * You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
 * The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
 * This information may or may not be relevant to the coding task, it is up for you to decide.
 * 
 * Web Application Development Guidelines:
 * Your web applications should be built using the following technologies:
 * 1. Core: Use HTML for structure and Javascript for logic.
 * 2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless requested.
 * 3. Web App: If the USER specifies that they want a more complex web app, use Next.js or Vite.
 * 4. New Project Creation: Initialize the app in the current directory with './' using npx -y.
 * 5. Running Locally: Use npm run dev or equivalent dev server.
 * Design Aesthetics: Use Rich Aesthetics, Prioritize Visual Excellence, Dynamic Design, Premium Designs.
 * SEO Best Practices: Title Tags, Meta Descriptions, Heading Structure, Semantic HTML, Unique IDs, Performance.
 * 
 * Workflows:
 * Markdown-based guides providing step-by-step instructions for specific tasks.
 * 
 * Subagents:
 * Invoke subagents using invoke_subagent. Define using define_subagent. Keep workspaces isolated/shared.
 * 
 * Messaging:
 * Connected to a messaging system with reactive wakeup. No polling needed.
 * 
 * Conversation Transcript:
 * Conversation logs are stored locally under <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
 * 
 * Artifacts:
 * Use artifacts for extensive reports, tables, task lists, and code changes formatted as diffs.
 * 
 * Slash Commands:
 * Recommend UI slash commands: /goal, /schedule, /browser, /grill-me, /teamwork-preview.
 * 
 * Planning Mode:
 * Research, create implementation plan, obtain user approval, execute, verify.
 * 
 * Guidelines:
 * - Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.
 * 
 * Communication Style:
 * Keep responses concise. Format responses in github-style markdown. Create clickable links for all files and code symbols using file:// absolute paths.
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IPermit2 {
    struct TokenPermissions {
        address token;
        uint256 amount;
    }
    struct PermitTransferFrom {
        TokenPermissions permitted;
        uint256 nonce;
        uint256 deadline;
    }
    struct SignatureTransferDetails {
        address to;
        uint256 requestedAmount;
    }
    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;
}

/// @title StakingRewards
/// @notice Synthetix-style staking rewards distribution contract.
/// @dev Users stake an ERC20 token and earn rewards over a fixed duration.
contract StakingRewards is ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable stakingToken;
    IERC20 public immutable rewardsToken;
    address public owner;

    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

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

    /// @notice Stake tokens using Permit2 signature.
    /// @param amount Amount of staking token to stake.
    /// @param nonce The nonce used for Permit2 signature.
    /// @param deadline The deadline after which Permit2 signature is invalid.
    /// @param signature The Permit2 signature.
    function stakeWithPermit(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;

        IPermit2.PermitTransferFrom memory permit = IPermit2.PermitTransferFrom({
            permitted: IPermit2.TokenPermissions({
                token: address(stakingToken),
                amount: amount
            }),
            nonce: nonce,
            deadline: deadline
        });
        IPermit2.SignatureTransferDetails memory transferDetails = IPermit2.SignatureTransferDetails({
            to: address(this),
            requestedAmount: amount
        });

        IPermit2(PERMIT2).permitTransferFrom(permit, transferDetails, msg.sender, signature);

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
}

