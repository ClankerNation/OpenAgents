// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract CompoundVault is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable baseToken;
    IERC20 public immutable rewardToken;
    address public strategy;
    address public feeRecipient;

    uint256 public totalShares;
    uint256 public totalDeposited;
    uint256 public performanceFeeBps;
    uint256 public lastHarvestTime;
    uint256 public lastPricePerShare;

    uint256 public constant FEE_MINIMUM = 1;
    uint256 public harvestThreshold;

    mapping(address => uint256) public userShares;

    event Deposited(address indexed user, uint256 amount, uint256 shares);
    event Withdrawn(address indexed user, uint256 amount, uint256 shares);
    event Harvested(uint256 profit, uint256 fee, uint256 timestamp);
    event Compounded(uint256 amount, uint256 newPricePerShare);

    constructor(
        address _baseToken,
        address _rewardToken,
        address _strategy,
        address _feeRecipient,
        uint256 _feeBps
    ) Ownable(msg.sender) {
        require(_feeBps <= 3000, "Vault: fee too high");
        baseToken = IERC20(_baseToken);
        rewardToken = IERC20(_rewardToken);
        strategy = _strategy;
        feeRecipient = _feeRecipient;
        performanceFeeBps = _feeBps;
        lastPricePerShare = 1e18;
    }

    function deposit(uint256 amount) external nonReentrant {
        require(amount > 0, "Vault: zero amount");

        uint256 sharesToMint;
        if (totalShares == 0) {
            sharesToMint = amount;
        } else {
            sharesToMint = (amount * totalShares) / totalDeposited;
        }

        baseToken.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesToMint;
        totalDeposited += amount;
        userShares[msg.sender] += sharesToMint;

        emit Deposited(msg.sender, amount, sharesToMint);
    }

    function withdraw(uint256 shareAmount) external nonReentrant {
        require(shareAmount > 0 && userShares[msg.sender] >= shareAmount, "Vault: invalid");

        uint256 assets = (shareAmount * totalDeposited) / totalShares;

        userShares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalDeposited -= assets;

        baseToken.safeTransfer(msg.sender, assets);
        emit Withdrawn(msg.sender, assets, shareAmount);
    }

    function harvest() external onlyOwner returns (uint256 profit) {
        uint256 rewardBalance = rewardToken.balanceOf(address(this));
        require(rewardBalance > 0, "Vault: nothing to harvest");

        uint256 currentPrice = pricePerShare();
        uint256 estimatedValue = (rewardBalance * currentPrice) / 1e18;

        require(estimatedValue >= harvestThreshold, "Vault: below threshold");

        uint256 fee = (estimatedValue * performanceFeeBps) / 10000;
        if (fee < FEE_MINIMUM && estimatedValue >= FEE_MINIMUM) {
            fee = FEE_MINIMUM;
        }
        profit = estimatedValue - fee;

        if (fee >= FEE_MINIMUM) {
            rewardToken.safeTransfer(feeRecipient, fee);
        }

        lastHarvestTime = block.timestamp;
        emit Harvested(profit, fee, block.timestamp);
    }

    function setHarvestThreshold(uint256 _threshold) external onlyOwner {
        harvestThreshold = _threshold;
    }

    function compound() external onlyOwner {
        uint256 beforeBase = baseToken.balanceOf(address(this));
        uint256 rewardBalance = rewardToken.balanceOf(address(this));
        if (rewardBalance == 0) return;

        uint256 compoundAmount = (rewardBalance * lastPricePerShare) / 1e18;

        totalDeposited += compoundAmount;
        lastPricePerShare = totalShares > 0 ? (totalDeposited * 1e18) / totalShares : 1e18;

        uint256 afterBase = baseToken.balanceOf(address(this));
        require(afterBase >= beforeBase, "Vault: negative yield");

        emit Compounded(compoundAmount, lastPricePerShare);
    }

    function setPerformanceFee(uint256 newFeeBps) external onlyOwner {
        require(newFeeBps <= 3000, "Vault: fee too high");
        performanceFeeBps = newFeeBps;
    }

    function setFeeRecipient(address _feeRecipient) external onlyOwner {
        require(_feeRecipient != address(0), "Vault: zero address");
        feeRecipient = _feeRecipient;
    }

    function pricePerShare() public view returns (uint256) {
        if (totalShares == 0) return 1e18;
        return (totalDeposited * 1e18) / totalShares;
    }
}
